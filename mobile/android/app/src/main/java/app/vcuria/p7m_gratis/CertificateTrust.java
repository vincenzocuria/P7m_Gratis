package app.vcuria.p7m_gratis;

import java.io.ByteArrayInputStream;
import java.security.KeyStore;
import java.security.cert.*;
import java.util.*;

/** Offline PKIX validation. Embedded certificates can never become trust anchors. */
public final class CertificateTrust {
    public static Map<String, Object> verify(byte[] leaf, List<byte[]> embedded, long time) {
        try {
            KeyStore system = KeyStore.getInstance("AndroidCAStore");
            system.load(null, null);
            Set<TrustAnchor> roots = new HashSet<>();
            Enumeration<String> aliases = system.aliases();
            while (aliases.hasMoreElements()) {
                java.security.cert.Certificate cert = system.getCertificate(aliases.nextElement());
                if (cert instanceof X509Certificate) roots.add(new TrustAnchor((X509Certificate)cert, null));
            }
            return verifyWithAnchors(leaf, embedded, time, roots);
        } catch (Exception e) {
            return answer(null, "Archivio di fiducia non disponibile", Collections.emptyList());
        }
    }

    public static Map<String, Object> verifyWithAnchors(byte[] leaf, List<byte[]> embedded,
                                                       long time, Set<TrustAnchor> roots) {
        try {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            X509Certificate signer = (X509Certificate)factory.generateCertificate(new ByteArrayInputStream(leaf));
            signer.checkValidity(new Date(time));
            boolean[] usage = signer.getKeyUsage();
            if (usage != null && !usage[0] && (usage.length < 2 || !usage[1])) {
                return answer(false, "Il certificato non permette la firma di documenti", Collections.emptyList());
            }
            List<X509Certificate> candidates = new ArrayList<>();
            candidates.add(signer);
            for (byte[] der : embedded) {
                candidates.add((X509Certificate)factory.generateCertificate(new ByteArrayInputStream(der)));
            }
            X509CertSelector selector = new X509CertSelector();
            selector.setCertificate(signer);
            PKIXBuilderParameters parameters = new PKIXBuilderParameters(roots, selector);
            parameters.setDate(new Date(time));
            parameters.setRevocationEnabled(false); // Authenticated OCSP/CRL is evaluated separately.
            parameters.setMaxPathLength(12);
            parameters.addCertStore(CertStore.getInstance("Collection", new CollectionCertStoreParameters(candidates)));
            PKIXCertPathBuilderResult validated = (PKIXCertPathBuilderResult)
                    CertPathBuilder.getInstance("PKIX").build(parameters);
            List<byte[]> chain = new ArrayList<>();
            for (java.security.cert.Certificate cert : validated.getCertPath().getCertificates()) chain.add(cert.getEncoded());
            X509Certificate root = validated.getTrustAnchor().getTrustedCert();
            if (root != null) chain.add(root.getEncoded());
            return answer(true, "Catena verificata con le radici del dispositivo", chain);
        } catch (CertificateExpiredException e) {
            return answer(false, "Certificato scaduto alla data della verifica", Collections.emptyList());
        } catch (CertificateNotYetValidException e) {
            return answer(false, "Certificato non ancora valido", Collections.emptyList());
        } catch (CertPathBuilderException e) {
            return answer(false, "Catena non attendibile o incompleta sul dispositivo", Collections.emptyList());
        } catch (Exception e) {
            return answer(null, "Validazione della catena non completata", Collections.emptyList());
        }
    }

    private static Map<String, Object> answer(Boolean trusted, String detail, List<byte[]> chain) {
        Map<String, Object> result = new HashMap<>();
        result.put("trusted", trusted);
        result.put("detail", detail);
        result.put("chain", chain);
        return result;
    }
}
