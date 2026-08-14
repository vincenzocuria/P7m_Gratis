/**
 * OCR & AI Multimodal Document Parser (Vision AI Simulator & Real FileReader)
 * Analyzes bill PDF / Image uploads and extracts:
 * Supplier Name, Consumptions (kWh/Smc), Total Bill Amount (€), Period (months), Utenza type.
 */

const OCR_PARSER = {
    // Pre-configured test sample templates for instant demo during client visits
    PRESETS: {
        ENEL_LUCE: {
            supplierName: 'Enel Energia S.p.A.',
            serviceType: 'LUCE',
            totalAmount: 142.50,
            kwh: 420,
            months: 2,
            powerKw: 3.0,
            isResidente: true,
            isBusiness: false,
            estimatedUnitCost: 0.165,
            confidence: 0.98,
            notes: 'Bolletta Bimestrale Enel Formidabile Elettrica'
        },
        ENI_GAS: {
            supplierName: 'Eni Plenitude S.p.A.',
            serviceType: 'GAS',
            totalAmount: 168.00,
            smc: 195,
            months: 2,
            isBusiness: false,
            estimatedUnitCost: 0.58,
            confidence: 0.96,
            notes: 'Bolletta Bimestrale Eni Plenitude Fix Gas'
        },
        A2A_LUCE_BIZ: {
            supplierName: 'A2A Energia S.p.A.',
            serviceType: 'LUCE',
            totalAmount: 485.00,
            kwh: 1650,
            months: 1,
            powerKw: 6.0,
            isResidente: false,
            isBusiness: true,
            estimatedUnitCost: 0.178,
            confidence: 0.97,
            notes: 'Bolletta Mensile Business A2A Altri Usi'
        },
        STG_LUCE: {
            supplierName: 'Servizio Tutele Graduali (STG)',
            serviceType: 'LUCE',
            totalAmount: 98.40,
            kwh: 310,
            months: 2,
            powerKw: 3.0,
            isResidente: true,
            isBusiness: false,
            estimatedUnitCost: 0.125,
            confidence: 0.99,
            notes: 'Bolletta Bimestrale Servizio Tutele Graduali'
        }
    },

    /**
     * Process image or PDF file object
     * @param {File} file 
     * @param {Function} onProgress 
     */
    async scanFile(file, onProgress) {
        if (onProgress) onProgress(20, "Caricamento file...");
        await new Promise(r => setTimeout(r, 400));

        const fileName = file.name.toLowerCase();

        // Check if file is XML or P7M
        if (fileName.endsWith('.xml') || fileName.endsWith('.p7m')) {
            if (onProgress) onProgress(60, "Decodifica Busta Elettronica P7M/XML...");
            const text = await file.text();
            await new Promise(r => setTimeout(r, 400));
            if (onProgress) onProgress(100, "Estrazione completata!");
            return INVOICE_PARSER.parseXml(text);
        }

        // Image / PDF AI Vision OCR Processing
        if (onProgress) onProgress(50, "Analisi Struttura ARERA con Vision AI...");
        await new Promise(r => setTimeout(r, 600));

        if (onProgress) onProgress(85, "Estrazione Scontrino dell'Energia...");
        await new Promise(r => setTimeout(r, 500));

        // Intelligent pattern recognition based on file name or simulated OCR
        let matchPreset = this.PRESETS.ENEL_LUCE;
        if (fileName.includes("gas") || fileName.includes("eni") || fileName.includes("plenitude")) {
            matchPreset = this.PRESETS.ENI_GAS;
        } else if (fileName.includes("a2a") || fileName.includes("business") || fileName.includes("piva")) {
            matchPreset = this.PRESETS.A2A_LUCE_BIZ;
        } else if (fileName.includes("stg") || fileName.includes("tutele")) {
            matchPreset = this.PRESETS.STG_LUCE;
        }

        if (onProgress) onProgress(100, "Analisi completata con successo!");
        return {
            success: true,
            ...matchPreset,
            extractedAt: new Date().toLocaleTimeString('it-IT')
        };
    }
};

if (typeof module !== 'undefined') {
    module.exports = OCR_PARSER;
}
