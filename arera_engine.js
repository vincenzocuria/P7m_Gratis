/**
 * ARERA Energy Calculation Engine (Luce & Gas)
 * Standardized for the Italian Energy Market (Mercato Libero vs STG vs Competitors)
 */

const ARERA_ENGINE = {
    // Current Default Market Indices (Updated for 2026)
    DEFAULT_INDICES: {
        PUN_MONO: 0.1085, // €/kWh (Prezzo Unico Nazionale Medio)
        PUN_F1: 0.1180,
        PUN_F2: 0.1090,
        PUN_F3: 0.0950,
        PSV_GAS: 0.3850,  // €/Smc (Punto di Scambio Virtuale)
        PERDITE_RETE_LUCE: 0.10 // 10% di perdite di rete per Bassa Tensione
    },

    // Standard ARERA Regulated Tariffs (Transport, System Charges & Taxes)
    REGULATED_TARIFFS: {
        LUCE: {
            // Trasporto e gestione contatore
            TRASP_FIXED_YEARLY: 21.60, // €/anno
            TRASP_POWER_YEARLY: 22.50, // €/kW/anno
            TRASP_ENERGY_KWH: 0.0112,  // €/kWh

            // Oneri di sistema (ASOS + ARIM)
            ONERI_RESIDENTE_KWH: 0.0335,
            ONERI_NON_RESIDENTE_FIXED_YEARLY: 13.50,
            ONERI_NON_RESIDENTE_KWH: 0.0335,

            // Imposte ed accise
            ACCISE_RESIDENTE_KWH: 0.0227, // Applicata oltre la soglia esente di 150 kWh/mese
            ACCISE_NON_RESIDENTE_KWH: 0.0227,
            SOGLIA_ESENTE_MONTHLY_KWH: 150,

            IVA_DOMESTICO: 0.10,
            IVA_BUSINESS: 0.22
        },
        GAS: {
            // Trasporto e gestione contatore
            TRASP_FIXED_YEARLY: 67.20, // €/anno
            TRASP_ENERGY_SMC: 0.0450,  // €/Smc medio

            // Oneri di sistema (RE, GS, UG1, UG2, UG3)
            ONERI_GAS_SMC: 0.0380,

            // Accisa Gas per Scaglioni annui
            ACCISE_TIERS: [
                { limit: 120, rate: 0.0440 },
                { limit: 480, rate: 0.1750 },
                { limit: 1560, rate: 0.1700 },
                { limit: Infinity, rate: 0.1860 }
            ],

            IVA_DOMESTICO_TIER_SMC: 480, // 10% fino a 480 Smc/anno, 22% oltre
            IVA_CIVILE_LOW: 0.10,
            IVA_HIGH: 0.22
        }
    },

    /**
     * Calculate Electricity Bill Breakdown
     * @param {Object} params 
     */
    calculateLuce(params) {
        const months = params.months || 1;
        const kwh = parseFloat(params.kwh) || 0;
        const powerKw = parseFloat(params.powerKw) || 3.0;
        const isResidente = params.isResidente !== false;
        const isBusiness = params.isBusiness || false;
        const pcvMonthly = parseFloat(params.pcvMonthly) || 9.0;
        const discountMonthly = parseFloat(params.discountMonthly) || 0;

        // 1. Spesa Materia Energia
        const pcvTotal = (pcvMonthly - discountMonthly) * months;
        let unitCostKwh = 0;
        if (params.tariffType === 'FIXED') {
            unitCostKwh = parseFloat(params.fixedPriceKwh) || 0.12;
        } else {
            const pun = parseFloat(params.punValue) || this.DEFAULT_INDICES.PUN_MONO;
            const spread = parseFloat(params.spreadKwh) || 0.015;
            const perdite = this.DEFAULT_INDICES.PERDITE_RETE_LUCE;
            unitCostKwh = (pun + spread) * (1 + perdite);
        }
        const quotaEnergiaMateria = kwh * unitCostKwh;
        const spesaMateriaEnergia = pcvTotal + quotaEnergiaMateria;

        // 2. Spesa Trasporto e Gestione Contatore
        const traspFixed = (this.REGULATED_TARIFFS.LUCE.TRASP_FIXED_YEARLY / 12) * months;
        const traspPower = (this.REGULATED_TARIFFS.LUCE.TRASP_POWER_YEARLY / 12) * powerKw * months;
        const traspEnergy = kwh * this.REGULATED_TARIFFS.LUCE.TRASP_ENERGY_KWH;
        const spesaTrasporto = traspFixed + traspPower + traspEnergy;

        // 3. Spesa Oneri di Sistema
        let oneriFixed = 0;
        let oneriRate = this.REGULATED_TARIFFS.LUCE.ONERI_RESIDENTE_KWH;
        if (!isResidente) {
            oneriFixed = (this.REGULATED_TARIFFS.LUCE.ONERI_NON_RESIDENTE_FIXED_YEARLY / 12) * months;
            oneriRate = this.REGULATED_TARIFFS.LUCE.ONERI_NON_RESIDENTE_KWH;
        }
        const spesaOneri = oneriFixed + (kwh * oneriRate);

        // 4. Imposte ed Accise
        let acciseTaxableKwh = kwh;
        if (isResidente) {
            const freeThreshold = this.REGULATED_TARIFFS.LUCE.SOGLIA_ESENTE_MONTHLY_KWH * months;
            acciseTaxableKwh = Math.max(0, kwh - freeThreshold);
        }
        const rateAccisa = isResidente ? this.REGULATED_TARIFFS.LUCE.ACCISE_RESIDENTE_KWH : this.REGULATED_TARIFFS.LUCE.ACCISE_NON_RESIDENTE_KWH;
        const spesaAccise = acciseTaxableKwh * rateAccisa;

        // Imponibile e IVA
        const imponibile = spesaMateriaEnergia + spesaTrasporto + spesaOneri + spesaAccise;
        const rateIva = isBusiness ? this.REGULATED_TARIFFS.LUCE.IVA_BUSINESS : this.REGULATED_TARIFFS.LUCE.IVA_DOMESTICO;
        const spesaIva = imponibile * rateIva;

        const totaleBolletta = imponibile + spesaIva;
        const costoMedioKwh = kwh > 0 ? (totaleBolletta / kwh) : 0;

        return {
            totaleBolletta: Math.round(totaleBolletta * 100) / 100,
            imponibile: Math.round(imponibile * 100) / 100,
            spesaMateriaEnergia: Math.round(spesaMateriaEnergia * 100) / 100,
            spesaMateriaQuotaFissa: Math.round(pcvTotal * 100) / 100,
            spesaMateriaQuotaEnergia: Math.round(quotaEnergiaMateria * 100) / 100,
            unitCostKwh: Math.round(unitCostKwh * 10000) / 10000,
            spesaTrasporto: Math.round(spesaTrasporto * 100) / 100,
            spesaOneri: Math.round(spesaOneri * 100) / 100,
            spesaAccise: Math.round(spesaAccise * 100) / 100,
            spesaIva: Math.round(spesaIva * 100) / 100,
            costoMedioKwh: Math.round(costoMedioKwh * 1000) / 1000,
            rateIvaPercent: rateIva * 100,
            kwh,
            months
        };
    },

    /**
     * Calculate Gas Bill Breakdown
     * @param {Object} params
     */
    calculateGas(params) {
        const months = params.months || 1;
        const smc = parseFloat(params.smc) || 0;
        const isBusiness = params.isBusiness || false;
        const qvdMonthly = parseFloat(params.qvdMonthly) || 10.0;
        const discountMonthly = parseFloat(params.discountMonthly) || 0;

        // 1. Spesa Materia Gas
        const qvdTotal = (qvdMonthly - discountMonthly) * months;
        let unitCostSmc = 0;
        if (params.tariffType === 'FIXED') {
            unitCostSmc = parseFloat(params.fixedPriceSmc) || 0.45;
        } else {
            const psv = parseFloat(params.psvValue) || this.DEFAULT_INDICES.PSV_GAS;
            const spread = parseFloat(params.spreadSmc) || 0.08;
            unitCostSmc = psv + spread;
        }
        const quotaEnergiaGas = smc * unitCostSmc;
        const spesaMateriaGas = qvdTotal + quotaEnergiaGas;

        // 2. Spesa Trasporto e Gestione Contatore
        const traspFixed = (this.REGULATED_TARIFFS.GAS.TRASP_FIXED_YEARLY / 12) * months;
        const traspEnergy = smc * this.REGULATED_TARIFFS.GAS.TRASP_ENERGY_SMC;
        const spesaTrasporto = traspFixed + traspEnergy;

        // 3. Spesa Oneri di Sistema
        const spesaOneri = smc * this.REGULATED_TARIFFS.GAS.ONERI_GAS_SMC;

        // 4. Accise Gas per Scaglioni
        let spesaAccise = 0;
        let remainingSmc = smc;
        let prevLimit = 0;
        for (const tier of this.REGULATED_TARIFFS.GAS.ACCISE_TIERS) {
            if (remainingSmc <= 0) break;
            const tierCapacity = (tier.limit - prevLimit) * (months / 12);
            const smcInTier = Math.min(remainingSmc, tierCapacity);
            spesaAccise += smcInTier * tier.rate;
            remainingSmc -= smcInTier;
            prevLimit = tier.limit;
        }

        // 5. Imponibile e IVA
        const imponibile = spesaMateriaGas + spesaTrasporto + spesaOneri + spesaAccise;
        
        let spesaIva = 0;
        if (isBusiness) {
            spesaIva = imponibile * 0.22;
        } else {
            const tier10Capacity = 480 * (months / 12);
            const smcLowIva = Math.min(smc, tier10Capacity);
            const smcHighIva = Math.max(0, smc - tier10Capacity);

            const ratioLow = smc > 0 ? (smcLowIva / smc) : 1;
            const imponibileLow = imponibile * ratioLow;

            spesaIva = (imponibileLow * 0.10) + ((imponibile - imponibileLow) * 0.22);
        }

        const totaleBolletta = imponibile + spesaIva;
        const costoMedioSmc = smc > 0 ? (totaleBolletta / smc) : 0;

        return {
            totaleBolletta: Math.round(totaleBolletta * 100) / 100,
            imponibile: Math.round(imponibile * 100) / 100,
            spesaMateriaGas: Math.round(spesaMateriaGas * 100) / 100,
            spesaMateriaQuotaFissa: Math.round(qvdTotal * 100) / 100,
            spesaMateriaQuotaEnergia: Math.round(quotaEnergiaGas * 100) / 100,
            unitCostSmc: Math.round(unitCostSmc * 10000) / 10000,
            spesaTrasporto: Math.round(spesaTrasporto * 100) / 100,
            spesaOneri: Math.round(spesaOneri * 100) / 100,
            spesaAccise: Math.round(spesaAccise * 100) / 100,
            spesaIva: Math.round(spesaIva * 100) / 100,
            costoMedioSmc: Math.round(costoMedioSmc * 1000) / 1000,
            smc,
            months
        };
    },

    /**
     * Compute Real Comparison between Current Bill and Proposed Target Offer
     */
    compareOffers(currentTotalInput, targetParams, type = 'LUCE') {
        const calcTarget = type === 'LUCE' 
            ? this.calculateLuce(targetParams) 
            : this.calculateGas(targetParams);

        const currentTotal = parseFloat(currentTotalInput) || 0;
        const targetTotal = calcTarget.totaleBolletta;
        const diffPeriod = currentTotal - targetTotal;
        
        const months = targetParams.months || 1;
        const diffYearly = diffPeriod * (12 / months);

        return {
            currentTotal: Math.round(currentTotal * 100) / 100,
            targetTotal,
            diffPeriod: Math.round(diffPeriod * 100) / 100,
            diffYearly: Math.round(diffYearly * 100) / 100,
            savingsPercent: currentTotal > 0 ? Math.round(((diffPeriod / currentTotal) * 100) * 10) / 10 : 0,
            isPositive: diffPeriod > 0,
            calcTarget
        };
    }
};

if (typeof module !== 'undefined') {
    module.exports = ARERA_ENGINE;
}
