/**
 * Client-side Electronic Invoice Parser (FatturaElettronica XML & P7M)
 * Extracts energy bill metrics (kWh, Smc, Total Cost, Supplier Name, Service Type)
 */

const INVOICE_PARSER = {
    /**
     * Parse raw XML string of Italian FatturaElettronica
     * @param {string} xmlText 
     */
    parseXml(xmlText) {
        try {
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(xmlText, "text/xml");

            const getElementValue = (parent, tag) => {
                const node = parent.getElementsByTagName(tag)[0];
                return node ? node.textContent.trim() : "";
            };

            // 1. Extract Supplier Info
            let supplierName = "Gestore Sconosciuto";
            const cedente = xmlDoc.getElementsByTagName("CedentePrestatore")[0];
            if (cedente) {
                const anagrafica = cedente.getElementsByTagName("Anagrafica")[0];
                if (anagrafica) {
                    supplierName = getElementValue(anagrafica, "Denominazione") || 
                        (getElementValue(anagrafica, "Nome") + " " + getElementValue(anagrafica, "Cognome")).trim();
                }
            }

            // 2. Extract Document Total & Date
            let totalAmount = 0;
            let invoiceDate = "";
            const datiGenerali = xmlDoc.getElementsByTagName("DatiGeneraliDocumento")[0];
            if (datiGenerali) {
                totalAmount = parseFloat(getElementValue(datiGenerali, "ImportoTotaleDocumento")) || 0;
                invoiceDate = getElementValue(datiGenerali, "Data");
            }

            // 3. Extract Line Items to detect kWh/Smc and Service Type (LUCE vs GAS)
            let serviceType = 'LUCE';
            let detectedKwh = 0;
            let detectedSmc = 0;
            let isBusiness = false;

            const dettaglioLinee = xmlDoc.getElementsByTagName("DettaglioLinee");
            let fullTextContent = xmlText.toLowerCase();

            if (fullTextContent.includes("gas") || fullTextContent.includes("smc") || fullTextContent.includes("pdr")) {
                serviceType = 'GAS';
            }

            for (let i = 0; i < dettaglioLinee.length; i++) {
                const line = dettaglioLinee[i];
                const desc = getElementValue(line, "Descrizione").toLowerCase();
                const qty = parseFloat(getElementValue(line, "Quantita")) || 0;
                const unitPrice = parseFloat(getElementValue(line, "PrezzoUnitario")) || 0;

                // Match kWh
                if (desc.includes("kwh") || desc.includes("energia elettrica")) {
                    if (qty > 0 && qty > detectedKwh) {
                        detectedKwh = qty;
                    }
                }
                // Match Smc
                if (desc.includes("smc") || desc.includes("mc") || desc.includes("gas")) {
                    if (qty > 0 && qty > detectedSmc) {
                        detectedSmc = qty;
                    }
                }

                // If total amount was not set in header, sum line totals
                if (totalAmount === 0) {
                    const lineTotal = parseFloat(getElementValue(line, "PrezzoTotale")) || 0;
                    totalAmount += lineTotal;
                }
            }

            // Fallback regex search if quantity was embedded in text
            if (serviceType === 'LUCE' && detectedKwh === 0) {
                const kwhMatch = fullTextContent.match(/(\d+[\.,]?\d*)\s*kwh/i);
                if (kwhMatch) detectedKwh = parseFloat(kwhMatch[1].replace(',', '.'));
            }
            if (serviceType === 'GAS' && detectedSmc === 0) {
                const smcMatch = fullTextContent.match(/(\d+[\.,]?\d*)\s*smc/i);
                if (smcMatch) detectedSmc = parseFloat(smcMatch[1].replace(',', '.'));
            }

            return {
                success: true,
                supplierName: supplierName || "Gestore Attuale",
                totalAmount: Math.round(totalAmount * 100) / 100,
                invoiceDate,
                serviceType,
                kwh: detectedKwh || 350,
                smc: detectedSmc || 85,
                rawXmlSnippet: xmlText.substring(0, 300)
            };
        } catch (err) {
            return {
                success: false,
                error: "Errore durante la lettura dell'XML della fattura: " + err.message
            };
        }
    }
};

if (typeof module !== 'undefined') {
    module.exports = INVOICE_PARSER;
}
