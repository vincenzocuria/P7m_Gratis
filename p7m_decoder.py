import os
import re
import mimetypes
import hashlib
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

try:
    from asn1crypto import cms, x509, core
    HAS_ASN1CRYPTO = True
except ImportError:
    HAS_ASN1CRYPTO = False

try:
    from cryptography import x509 as crypto_x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

try:
    from services.signature.crypto_verifier import CryptoVerifier
    from services.signature.cert_chain import CertificateChainValidator
    from services.signature.trusted_list import TrustedListChecker
    from services.signature.revocation import RevocationChecker
    from services.signature.timestamp import TimestampValidator
    from services.signature.trust import validate_path, find_issuer, system_roots
    HAS_SIGNATURE_SERVICES = True
except ImportError:
    HAS_SIGNATURE_SERVICES = False

try:
    from services.signature.pades import extract_pades_signatures
    from services.signature.xmldsig import verify_xml_signatures
    from services.signature.asic import inspect_asic, manifest_digest_error
    HAS_CONTAINER_SIGNATURES = True
except ImportError:
    HAS_CONTAINER_SIGNATURES = False


class P7MDecoder:
    """
    Decodes PKCS#7 / CMS / CAdES (.p7m) envelopes and extracts:
    1. Original payload bytes
    2. Real MIME type and extension
    3. Signer details & Certificate info
    """

    # Same cap as the mobile viewer: peel at most eight SignedData envelopes.
    MAX_NESTED_ENVELOPES = 8

    @staticmethod
    def is_p7m_file(filepath: str) -> bool:
        ext = os.path.splitext(filepath)[1].lower()
        return ext in ('.p7m', '.p7s', '.p7c', '.p7b')

    @classmethod
    def decode_file(cls, filepath_or_bytes: Any, detached_content: Optional[bytes] = None) -> Dict[str, Any]:
        """
        Decodes a p7m file or raw p7m bytes.
        Returns a dict with:
        - success: bool
        - error: Optional[str]
        - payload: bytes
        - mime_type: str
        - ext: str
        - suggested_filename: str
        - sha256: str
        - signer_info: dict
        """
        if isinstance(filepath_or_bytes, str):
            original_filename = os.path.basename(filepath_or_bytes)
            try:
                with open(filepath_or_bytes, 'rb') as f:
                    data = f.read()
            except OSError as exc:
                return {'success': False, 'error': str(exc), 'original_filename': original_filename}
        else:
            original_filename = "document.p7m"
            data = filepath_or_bytes

        # Clean PEM header if raw text PEM
        data_clean = cls._strip_pem_if_needed(data)
        container_name = None
        signature_format = None
        allow_nested = True

        asic = cls._open_asic(data_clean) if HAS_CONTAINER_SIGNATURES else None
        if isinstance(asic, dict) and "payload" not in asic:
            return {
                "success": False,
                "error": asic.get("error") or "Contenitore ASiC non apribile.",
                "original_filename": original_filename,
            }
        if isinstance(asic, dict):
            payload = asic["payload"]
            certificates = asic["certificates"]
            signer_metas = asic["signers"]
            error = asic["error"]
            container_name = asic["name"]
            signature_format = asic["format"]
            allow_nested = False
        else:
            # Try extracting payload & certificates
            payload, certificates, signer_metas, error = cls._extract_pkcs7(data_clean)

            if payload is None and cls._is_signed_data(data_clean):
                if detached_content is None and isinstance(filepath_or_bytes, str):
                    sibling = re.sub(r'(?i)\.p7s$', '', filepath_or_bytes)
                    if sibling != filepath_or_bytes and os.path.isfile(sibling):
                        try:
                            with open(sibling, 'rb') as handle:
                                detached_content = handle.read()
                        except OSError:
                            detached_content = None
                if detached_content is None:
                    return {
                        "success": False,
                        "needs_detached_content": True,
                        "error": "Firma detached: selezionare il documento originale.",
                        "original_filename": original_filename,
                    }
                payload, certificates, signer_metas, error = cls._extract_pkcs7(
                    data_clean, external_payload=detached_content, require_detached=True
                )
                signature_format = "CAdES detached"
                if payload is None:
                    return {
                        "success": False,
                        "error": error or "Impossibile verificare la firma detached.",
                        "original_filename": original_filename,
                    }

            if payload is None and not data_clean.startswith(b"%PDF-") and not cls._looks_like_xml(data_clean):
                # Fallback attempt: scan binary data for known magic headers (%PDF-, <?xml, etc.)
                payload = cls._fallback_extract_raw(data_clean)
                if payload:
                    error = "Payload estratto tramite scansione raw del contenitore PKCS#7."

            # Support direct PDF / PAdES files or un-enveloped documents
            if payload is None:
                if data_clean.startswith(b"%PDF-"):
                    payload = data_clean
                    signer_metas, error, verified = cls._read_pades(data_clean)
                    signature_format = "PAdES" if verified else None
                    allow_nested = False
                elif b"<?xml" in data_clean[:500] or data_clean.startswith(b"\x89PNG") or data_clean.startswith(b"\xff\xd8\xff"):
                    payload = data_clean
                    if b"<?xml" in data_clean[:500] or data_clean.lstrip().startswith(b"<"):
                        xml_results = verify_xml_signatures(data_clean) if HAS_CONTAINER_SIGNATURES else []
                        if xml_results:
                            signer_metas, certificates = cls._signers_from_xml(xml_results)
                            signature_format = "XAdES" if any(item.get("profile") == "XAdES" for item in xml_results) else "XML-DSig"
                            error = None
                            allow_nested = False
                        else:
                            info = cls._empty_signer_info()
                            info['signer_name'] = "Documento Diretto (Non in busta CAdES/P7M)"
                            signer_metas = [info]
                            error = None
                    else:
                        info = cls._empty_signer_info()
                        info['signer_name'] = "Documento Diretto (Non in busta CAdES/P7M)"
                        signer_metas = [info]
                        error = None

        if payload is None:
            return {
                "success": False,
                "error": error or "Impossibile decodificare la busta PKCS#7 / P7M.",
                "original_filename": original_filename
            }

        # Nested CAdES (.p7m.p7m): the first payload is another SignedData.
        # Stop on a detached inner envelope (no eContent) and keep that payload.
        depth = 1
        while allow_nested and cls._is_signed_data(payload):
            if depth >= cls.MAX_NESTED_ENVELOPES:
                return {
                    "success": False,
                    "error": "Troppe buste P7M annidate",
                    "original_filename": original_filename
                }
            inner_payload, inner_certs, inner_signers, inner_error = cls._extract_pkcs7(payload)
            if inner_payload is None:
                break
            payload = inner_payload
            certificates.extend(inner_certs)
            signer_metas.extend(inner_signers)
            if inner_error:
                error = inner_error
            depth += 1

        # Calculate payload hash
        payload_hash = hashlib.sha256(payload).hexdigest()

        # Determine MIME type and suggested filename
        mime_type, ext = cls.detect_mime_type(payload)
        inner_name = cls._suggested_filename((container_name + ".p7m") if container_name else original_filename, ext)

        # Extract primary signer details
        primary_signer = signer_metas[0] if signer_metas else cls._empty_signer_info()

        return {
            "success": True,
            "error": error,
            "original_filename": original_filename,
            "suggested_filename": inner_name,
            "payload": payload,
            "payload_size": len(payload),
            "mime_type": mime_type,
            "ext": ext,
            "sha256": payload_hash,
            "signer_info": primary_signer,
            "all_signers": signer_metas,
            "certificate_count": len(certificates),
            "signature_format": signature_format,
        }

    @classmethod
    def _looks_like_xml(cls, data: bytes) -> bool:
        sample = data.lstrip(b"\xef\xbb\xbf \t\r\n")
        return sample.startswith((b"<?xml", b"<"))

    @classmethod
    def _is_signed_data(cls, data: bytes) -> bool:
        """True when the entire buffer is one CMS ContentInfo of type signedData."""
        if not data or data[:1] != b'\x30' or not HAS_ASN1CRYPTO:
            return False
        try:
            content_info = cms.ContentInfo.load(data, strict=True)
            return content_info['content_type'].native == 'signed_data'
        except Exception:
            return False

    @classmethod
    def _suggested_filename(cls, original_filename: str, ext: str) -> str:
        """Drop every trailing .p7m and apply the detected extension if none remains."""
        stripped = re.sub(r'(?i)(?:\.p7m)+$', '', original_filename)
        stripped = re.sub(r'(?i)(?:\.p7s)+$', '', stripped)
        if stripped and stripped != original_filename:
            inner_name = stripped
        else:
            inner_name = f"estratto{ext}"
        
        known_extensions = {'.pdf', '.xml', '.png', '.jpg', '.jpeg', '.gif', 
                           '.docx', '.xlsx', '.zip', '.json', '.html', '.txt', '.bin'}
        
        inner_lower = inner_name.lower()
        has_known_ext = any(inner_lower.endswith(known_ext) for known_ext in known_extensions)
        
        if not has_known_ext and ext:
            inner_name += ext
        
        return inner_name

    @classmethod
    def _strip_pem_if_needed(cls, data: bytes) -> bytes:
        if b"-----BEGIN PKCS7-----" in data or b"-----BEGIN CMS-----" in data:
            import base64
            lines = data.decode('ascii', errors='ignore').splitlines()
            b64_lines = [l.strip() for l in lines if not l.startswith('-----')]
            try:
                return base64.b64decode(''.join(b64_lines))
            except Exception:
                pass
        return data

    @classmethod
    def _describe_signer(cls, cert, certificates, crypto_res, signer_info=None) -> Dict[str, Any]:
        cert_meta = CertificateChainValidator.parse_certificate_meta(cert) if cert is not None else {}
        qtsp_res = TrustedListChecker.is_qtsp_qualified(cert_meta.get("issuer", ""), cert_meta.get("organization", ""))
        trust_res = validate_path(cert, certificates)
        issuer = find_issuer(cert, list(certificates) + list(system_roots()))
        rev_res = RevocationChecker.check_revocation(cert, issuer=issuer)
        if signer_info is not None:
            ts_res = TimestampValidator.extract_timestamp(signer_info)
        else:
            ts_res = {"present": False, "valid": False, "message": None, "timestamp_date": None, "tsa_name": None}
        meta = cls._empty_signer_info()
        meta.update({
            "signer_name": cert_meta.get("signer_name", "Firmatario Sconosciuto"),
            "tax_code": cert_meta.get("tax_code"),
            "organization": cert_meta.get("organization"),
            "issuer": cert_meta.get("issuer"),
            "valid_from": cert_meta.get("valid_from"),
            "valid_to": cert_meta.get("valid_until"),
            "is_expired": not cert_meta.get("is_valid_now", True),
            "chain_trusted": trust_res["trusted"],
            "chain_error": trust_res["error"],
            "timestamp_message": ts_res.get("message"),
            "crypto_valid": crypto_res.get("crypto_valid", False),
            "digest_matches": crypto_res.get("digest_matches", False),
            "algorithm": crypto_res.get("algorithm", "RSA-SHA256"),
            "is_qtsp_qualified": qtsp_res.get("is_qualified", False),
            "qtsp_name": qtsp_res.get("qtsp_name", "Sconosciuto"),
            "revocation_status": rev_res.get("status", "UNCHECKED_OFFLINE"),
            "revocation_message": rev_res.get("message"),
            "timestamp_present": ts_res.get("present", False),
            "timestamp_valid": ts_res.get("valid", False),
            "timestamp_date": ts_res.get("timestamp_date"),
            "timestamp_tsa": ts_res.get("tsa_name"),
            "validation_error": crypto_res.get("error"),
        })
        return meta

    @classmethod
    def _unverified_signer(cls, name: str, message: str) -> Dict[str, Any]:
        info = cls._empty_signer_info()
        info["signer_name"] = name
        info["validation_error"] = message
        return info

    @classmethod
    def _signers_from_xml(cls, results) -> Tuple[list, list]:
        metas = []
        certificates = []
        for result in results:
            asn_certs = []
            for der in result.get("certificates") or []:
                try:
                    asn_certs.append(x509.Certificate.load(der))
                except Exception:
                    continue
            crypto_res = {
                "crypto_valid": result.get("crypto_valid"),
                "digest_matches": result.get("digest_matches"),
                "algorithm": result.get("algorithm") or result.get("profile") or "XML-DSig",
                "error": result.get("error"),
            }
            if HAS_SIGNATURE_SERVICES and asn_certs:
                metas.append(cls._describe_signer(asn_certs[0], asn_certs, crypto_res))
                certificates.extend(asn_certs)
            else:
                meta = cls._unverified_signer(result.get("profile") or "Firma XML", result.get("error") or "Firma XML non verificabile")
                meta["crypto_valid"] = result.get("crypto_valid")
                meta["digest_matches"] = result.get("digest_matches")
                meta["algorithm"] = crypto_res["algorithm"]
                metas.append(meta)
        return metas, certificates

    @classmethod
    def _read_pades(cls, pdf: bytes):
        signatures = extract_pades_signatures(pdf) if HAS_CONTAINER_SIGNATURES else []
        covering = [item for item in signatures if item["supported"] and item["covers_document"]]
        if covering:
            metas = []
            for item in covering:
                _, _, signers, cms_error = cls._extract_pkcs7(
                    item["cms"], external_payload=item["signed_bytes"], require_detached=True
                )
                if signers:
                    metas.extend(signers)
                else:
                    failed = cls._unverified_signer("Firma PAdES", cms_error or "CMS PAdES illeggibile")
                    failed["crypto_valid"] = False
                    failed["digest_matches"] = False
                    metas.append(failed)
            verified = any(item.get("crypto_valid") and item.get("digest_matches") for item in metas)
            message = "Firma PAdES verificata sul ByteRange dell'intero PDF." if verified else "Firma PAdES non valida."
            return metas, message, True
        if signatures:
            message = signatures[0]["error"] or "Firma PAdES non verificabile."
            return [cls._unverified_signer("Firma PAdES", message)], message, True
        detected = cls.detect_pades_signature(pdf)
        if detected:
            return [detected], "Documento PDF con firma digitale PAdES.", False
        info = cls._empty_signer_info()
        info["signer_name"] = "Documento PDF Diretto (Senza Firma CAdES/P7M)"
        return [info], None, False

    @classmethod
    def _open_asic(cls, data: bytes):
        try:
            package = inspect_asic(data)
        except ValueError as exc:
            return {"error": str(exc)}
        if package is None:
            return None
        files = package["files"]
        signers = []
        certificates = []
        notes = []
        for name in package["cades"]:
            manifest_name = None
            for candidate in package["manifests"]:
                if os.path.basename(name) in files[candidate].decode("utf-8", "replace"):
                    manifest_name = candidate
                    break
            if manifest_name is None and len(package["manifests"]) == 1 and len(package["cades"]) == 1:
                manifest_name = package["manifests"][0]
            if manifest_name:
                signed_name = manifest_name
                digest_error = manifest_digest_error(files[manifest_name], files)
            elif len(package["data_files"]) == 1:
                signed_name = package["data_files"][0]
                digest_error = None
            else:
                signers.append(cls._unverified_signer("Firma ASiC", "Contenuto della firma CAdES non determinato"))
                continue
            _, certs, metas, error = cls._extract_pkcs7(files[name], external_payload=files[signed_name], require_detached=True)
            certificates.extend(certs)
            if not metas:
                signers.append(cls._unverified_signer("Firma ASiC", error or "Firma CAdES illeggibile"))
            else:
                if digest_error:
                    for meta in metas:
                        meta["digest_matches"] = False
                        meta["validation_error"] = digest_error
                signers.extend(metas)
        for name in package["xades"]:
            xml_results = verify_xml_signatures(files[name], files)
            if not xml_results:
                signers.append(cls._unverified_signer("Firma XAdES", "Firma XML assente nel contenitore"))
                continue
            metas, certs = cls._signers_from_xml(xml_results)
            signers.extend(metas)
            certificates.extend(certs)
        if not signers:
            signers.append(cls._unverified_signer("Contenitore ASiC", "Nessuna firma verificabile nel contenitore"))
        return {
            "payload": package["preview"],
            "signers": signers,
            "certificates": certificates,
            "name": package["preview_name"],
            "format": package["profile"],
            "error": None,
        }

    @classmethod
    def _extract_pkcs7(cls, data: bytes, external_payload: Optional[bytes] = None, require_detached: bool = False) -> Tuple[Optional[bytes], list, list, Optional[str]]:
        certificates = []
        signer_metas = []

        if HAS_ASN1CRYPTO:
            try:
                content_info = cms.ContentInfo.load(data)
                content_type = content_info['content_type'].native
                
                if content_type == 'signed_data':
                    signed_data = content_info['content']
                    encap_info = signed_data['encap_content_info']
                    
                    # Extract eContent
                    econtent = encap_info['content']
                    payload = None
                    if econtent is not None:
                        payload = econtent.native
                        if isinstance(payload, bytes):
                            pass
                        elif isinstance(payload, core.Asn1Value):
                            payload = payload.dump()
                    
                    # Certificates
                    certs_raw = signed_data['certificates']
                    if certs_raw:
                        for cert_choice in certs_raw:
                            if cert_choice.name == 'certificate':
                                certificates.append(cert_choice.chosen)

                    if require_detached and payload is not None:
                        return None, certificates, [], "La busta CMS non è una firma detached."
                    if payload is None:
                        payload = external_payload

                    # Process SignerInfos
                    signer_infos = signed_data['signer_infos']
                    if signer_infos and payload is not None:
                        for sinfo in signer_infos:
                            if HAS_SIGNATURE_SERVICES and certificates:
                                cert = CertificateChainValidator.match_signer_certificate(sinfo, certificates)
                                crypto_res = CryptoVerifier.verify_signer(sinfo, cert, payload, expected_content_type=encap_info["content_type"].native)
                                signer_metas.append(cls._describe_signer(cert, certificates, crypto_res, sinfo))
                            elif certificates:
                                meta = cls._parse_asn1crypto_cert(certificates[0])
                                signer_metas.append(meta)
                            else:
                                signer_metas.append(cls._empty_signer_info())

                    elif certificates:
                        for cert in certificates:
                            signer_metas.append(cls._parse_asn1crypto_cert(cert))

                    return payload, certificates, signer_metas, None
            except Exception as e:
                pass

        if HAS_CRYPTOGRAPHY:
            try:
                # Load PKCS7 using cryptography
                pkcs7_obj = pkcs7.load_der_pkcs7_certificates(data)
                # Note: cryptography pkcs7 load_der_pkcs7_certificates gets certs, but getting payload requires asn1
                if pkcs7_obj:
                    for cert in pkcs7_obj:
                        meta = cls._parse_crypto_cert(cert)
                        signer_metas.append(meta)
                        certificates.append(cert)
            except Exception:
                pass

        return None, certificates, signer_metas, "Formato ASN.1 non riconosciuto direttamente con asn1crypto."

    @classmethod
    def _parse_asn1crypto_cert(cls, cert) -> Dict[str, Any]:
        info = cls._empty_signer_info()
        try:
            subject = cert.subject.native
            info['common_name'] = subject.get('common_name', '')
            info['organization'] = subject.get('organization_name', '')
            info['organization_unit'] = subject.get('organizational_unit_name', '')
            info['country'] = subject.get('country_name', '')
            info['given_name'] = subject.get('given_name', '')
            info['surname'] = subject.get('surname', '')
            info['serial_number'] = subject.get('serial_number', '')

            # Full Subject Display
            cn = info['common_name'] or f"{info['given_name']} {info['surname']}".strip()
            info['signer_name'] = cn or "Firmatario Sconosciuto"

            # Check Codice Fiscale in serialNumber or subject attributes
            cf = ""
            if 'serial_number' in subject and isinstance(subject['serial_number'], str):
                sn = subject['serial_number']
                if sn.startswith("TINIT-"):
                    cf = sn.replace("TINIT-", "")
                elif len(sn) == 16 and sn.isalnum():
                    cf = sn
            if not cf and 'dn_qualifier' in subject:
                cf = subject['dn_qualifier']
            info['tax_code'] = cf

            # Issuer
            issuer = cert.issuer.native
            info['issuer'] = issuer.get('common_name', issuer.get('organization_name', 'CA Sconosciuta'))

            # Validity
            val = cert['tbs_certificate']['validity']
            info['valid_from'] = val['not_before'].native.strftime('%d/%m/%Y %H:%M:%S')
            info['valid_to'] = val['not_after'].native.strftime('%d/%m/%Y %H:%M:%S')
            
            # Check if currently valid date
            now = datetime.now(val['not_before'].native.tzinfo)
            info['is_expired'] = not (val['not_before'].native <= now <= val['not_after'].native)

        except Exception as e:
            info['signer_name'] = "Certificato Presente (Dettagli non leggibili)"
        
        return info

    @classmethod
    def _parse_crypto_cert(cls, cert) -> Dict[str, Any]:
        info = cls._empty_signer_info()
        try:
            subject = cert.subject
            for attr in subject:
                oid = attr.oid._name
                val = attr.value
                if oid == 'commonName':
                    info['common_name'] = val
                elif oid == 'organizationName':
                    info['organization'] = val
                elif oid == 'serialNumber':
                    info['serial_number'] = val

            info['signer_name'] = info['common_name'] or "Firmatario Sconosciuto"
            info['valid_from'] = cert.not_valid_before_utc.strftime('%d/%m/%Y %H:%M:%S')
            info['valid_to'] = cert.not_valid_after_utc.strftime('%d/%m/%Y %H:%M:%S')
        except Exception:
            pass
        return info

    @staticmethod
    def _empty_signer_info() -> Dict[str, Any]:
        return {
            "signer_name": "Non specificato",
            "common_name": "",
            "given_name": "",
            "surname": "",
            "tax_code": "",
            "organization": "",
            "organization_unit": "",
            "country": "",
            "serial_number": "",
            "issuer": "",
            "valid_from": "-",
            "valid_to": "-",
            "is_expired": False,
            "crypto_valid": None,
            "digest_matches": None,
            "algorithm": "Non verificato",
            "is_qtsp_qualified": None,
            "qtsp_name": "Non verificato",
            "revocation_status": "UNKNOWN",
            "revocation_message": "Revoca non verificata",
            "chain_trusted": None,
            "chain_error": "Catena non verificata",
            "timestamp_present": False,
            "timestamp_valid": False,
            "timestamp_date": None,
            "timestamp_tsa": None,
            "validation_error": None
        }

    @classmethod
    def _fallback_extract_raw(cls, data: bytes) -> Optional[bytes]:
        """
        Scans binary data for embedded file headers like %PDF-, <?xml, etc.
        """
        # Try finding PDF
        pdf_idx = data.find(b'%PDF-')
        if pdf_idx != -1:
            eof_idx = data.rfind(b'%%EOF')
            if eof_idx != -1 and eof_idx > pdf_idx:
                return data[pdf_idx:eof_idx + 5]
            else:
                return data[pdf_idx:]

        # Try finding XML
        xml_idx = data.find(b'<?xml')
        if xml_idx != -1:
            xml_end = data.rfind(b'>')
            if xml_end > xml_idx:
                return data[xml_idx:xml_end + 1]

        # Try finding PNG
        png_idx = data.find(b'\x89PNG\r\n\x1a\n')
        if png_idx != -1:
            iend_idx = data.rfind(b'IEND')
            if iend_idx != -1:
                return data[png_idx:iend_idx + 8]
            return data[png_idx:]

        # Try finding JPEG
        jpg_idx = data.find(b'\xff\xd8\xff')
        if jpg_idx != -1:
            eoi_idx = data.rfind(b'\xff\xd9')
            if eoi_idx != -1:
                return data[jpg_idx:eoi_idx + 2]
            return data[jpg_idx:]

        return None

    @classmethod
    def detect_pades_signature(cls, pdf_bytes: bytes) -> Optional[Dict[str, Any]]:
        if b"/ByteRange" in pdf_bytes or b"/Type /Sig" in pdf_bytes or b"/SubFilter" in pdf_bytes:
            info = cls._empty_signer_info()
            info['signer_name'] = "Firma Digitale PAdES (Incorporata nel PDF)"
            info['issuer'] = "Certificato PAdES PDF"

            import re
            name_match = re.search(rb'/Name\s*\((.*?)\)', pdf_bytes)
            if name_match:
                try:
                    info['signer_name'] = name_match.group(1).decode('utf-8', errors='ignore')
                except Exception:
                    pass

            contact_match = re.search(rb'/ContactInfo\s*\((.*?)\)', pdf_bytes)
            if contact_match:
                try:
                    info['tax_code'] = contact_match.group(1).decode('utf-8', errors='ignore')
                except Exception:
                    pass

            reason_match = re.search(rb'/Reason\s*\((.*?)\)', pdf_bytes)
            if reason_match:
                try:
                    info['organization'] = f"Motivo: {reason_match.group(1).decode('utf-8', errors='ignore')}"
                except Exception:
                    pass

            return info
        return None


    @classmethod
    def detect_mime_type(cls, payload: bytes) -> Tuple[str, str]:
        """
        Determines MIME type and file extension from payload bytes.
        """
        # PDF check
        if payload.startswith(b'%PDF-'):
            return 'application/pdf', '.pdf'

        # XML check
        stripped = payload.strip()
        if stripped.startswith(b'<?xml') or (stripped.startswith(b'<') and stripped.endswith(b'>')):
            return 'text/xml', '.xml'

        # PNG check
        if payload.startswith(b'\x89PNG'):
            return 'image/png', '.png'

        # JPEG check
        if payload.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg', '.jpg'

        # GIF check
        if payload.startswith(b'GIF87a') or payload.startswith(b'GIF89a'):
            return 'image/gif', '.gif'

        # ZIP / DOCX / XLSX check
        if payload.startswith(b'PK\x03\x04'):
            if b'word/' in payload[:2000]:
                return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'
            elif b'xl/' in payload[:2000]:
                return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'
            return 'application/zip', '.zip'

        # JSON check
        if (stripped.startswith(b'{') and stripped.endswith(b'}')) or (stripped.startswith(b'[') and stripped.endswith(b']')):
            try:
                import json
                json.loads(payload.decode('utf-8'))
                return 'application/json', '.json'
            except Exception:
                pass

        # Text UTF-8 check
        try:
            decoded = payload.decode('utf-8')
            printable_ratio = sum(1 for c in decoded if c.isprintable() or c in '\r\n\t') / max(1, len(decoded))
            if printable_ratio > 0.90:
                if '<html' in decoded.lower():
                    return 'text/html', '.html'
                return 'text/plain', '.txt'
        except UnicodeDecodeError:
            pass

        return 'application/octet-stream', '.bin'
