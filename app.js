/**
 * EnergyCompare Pro - Main Application Logic & Controller
 */

// Agency Portfolio Offers Catalog State
let catalogOffers = [
    {
        id: 'luce_fix_1',
        type: 'LUCE',
        name: '⚡ Luce Verde Fissa 12M',
        tariffType: 'FIXED',
        fixedPriceKwh: 0.118,
        pcvMonthly: 9.0,
        discountMonthly: 1.5, // Sconto RID/Bolletta Web
        description: 'Prezzo Bloccato 1 Anno + 18€/anno sconto digitale'
    },
    {
        id: 'luce_var_1',
        type: 'LUCE',
        name: '📈 Luce Flex Indicizzata (PUN + 0.012)',
        tariffType: 'INDEXED',
        punValue: 0.1085,
        spreadKwh: 0.012,
        pcvMonthly: 8.5,
        discountMonthly: 0,
        description: 'Trasparenza Indice PUN con Spread minimo'
    },
    {
        id: 'gas_fix_1',
        type: 'GAS',
        name: '🔥 Gas Casa Fissa 12M',
        tariffType: 'FIXED',
        fixedPriceSmc: 0.420,
        qvdMonthly: 10.0,
        discountMonthly: 2.0,
        description: 'Prezzo Smc Bloccato + 24€/anno sconto fedeltà'
    },
    {
        id: 'gas_var_1',
        type: 'GAS',
        name: '📊 Gas Flex Indicizzato (PSV + 0.065)',
        tariffType: 'INDEXED',
        psvValue: 0.385,
        spreadSmc: 0.065,
        qvdMonthly: 9.5,
        discountMonthly: 0,
        description: 'Prezzo indicizzato al mercato PSV mensile'
    }
];

let chartLuceInstance = null;
let chartGasInstance = null;

// Application Initialization
document.addEventListener('DOMContentLoaded', () => {
    populateOfferSelectors();
    renderCatalogList();
    recalculateLuce();
    recalculateGas();
});

// View Mode Toggle (Desktop vs Smartphone Simulator Frame)
function setDeviceView(mode) {
    const frame = document.getElementById('appFrame');
    const btnDesktop = document.getElementById('btnViewDesktop');
    const btnMobile = document.getElementById('btnViewMobile');

    if (mode === 'mobile') {
        frame.className = 'mobile-frame';
        btnMobile.classList.add('active');
        btnDesktop.classList.remove('active');
    } else {
        frame.className = 'desktop-view';
        btnDesktop.classList.add('active');
        btnMobile.classList.remove('active');
    }
}

// Theme Toggle (Dark vs Light)
function toggleTheme() {
    document.body.classList.toggle('light-theme');
    const btnIcon = document.querySelector('#btnThemeToggle i');
    if (document.body.classList.contains('light-theme')) {
        btnIcon.className = 'fa-solid fa-sun';
    } else {
        btnIcon.className = 'fa-solid fa-moon';
    }
}

// Tab Switching
function switchTab(tabId) {
    document.querySelectorAll('.nav-tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.add('hidden'));

    const activeBtn = document.querySelector(`.nav-tab-btn[data-tab="${tabId}"]`);
    const activePane = document.getElementById(`pane-${tabId}`);

    if (activeBtn) activeBtn.classList.add('active');
    if (activePane) activePane.classList.remove('hidden');

    if (tabId === 'preventivo') {
        updateQuoteSheet();
    }
}

// Populate Dynamic Selectors
function populateOfferSelectors() {
    const selLuce = document.getElementById('selectOfferLuce');
    const selGas = document.getElementById('selectOfferGas');

    if (selLuce) {
        selLuce.innerHTML = catalogOffers
            .filter(o => o.type === 'LUCE')
            .map(o => `<option value="${o.id}">${o.name}</option>`)
            .join('');
    }
    if (selGas) {
        selGas.innerHTML = catalogOffers
            .filter(o => o.type === 'GAS')
            .map(o => `<option value="${o.id}">${o.name}</option>`)
            .join('');
    }
}

// Load Demo Presets
function loadDemoPreset(presetKey) {
    const preset = OCR_PARSER.PRESETS[presetKey];
    if (!preset) return;

    if (preset.serviceType === 'LUCE') {
        switchTab('luce');
        document.getElementById('inputKwh').value = preset.kwh;
        document.getElementById('inputTotalLuce').value = preset.totalAmount;
        document.getElementById('inputMonthsLuce').value = preset.months;
        document.getElementById('inputPowerKw').value = preset.powerKw || 3.0;
        document.getElementById('supplierBadgeLuce').textContent = preset.supplierName;
        recalculateLuce();
    } else {
        switchTab('gas');
        document.getElementById('inputSmc').value = preset.smc;
        document.getElementById('inputTotalGas').value = preset.totalAmount;
        document.getElementById('inputMonthsGas').value = preset.months;
        document.getElementById('supplierBadgeGas').textContent = preset.supplierName;
        recalculateGas();
    }
}

// Upload & OCR Scan File Handler
async function handleFileUpload(event, serviceType) {
    const file = event.target.files[0];
    if (!file) return;

    const overlay = document.getElementById('scanProgressOverlay');
    const statusTitle = document.getElementById('scanStatusTitle');
    const statusSubtext = document.getElementById('scanStatusSubtext');

    overlay.classList.remove('hidden');

    try {
        const result = await OCR_PARSER.scanFile(file, (progress, text) => {
            statusTitle.textContent = text;
            statusSubtext.textContent = `Elaborazione ${progress}%`;
        });

        overlay.classList.add('hidden');

        if (result.success) {
            if (serviceType === 'LUCE' || result.serviceType === 'LUCE') {
                switchTab('luce');
                if (result.kwh) document.getElementById('inputKwh').value = result.kwh;
                if (result.totalAmount) document.getElementById('inputTotalLuce').value = result.totalAmount;
                if (result.supplierName) document.getElementById('supplierBadgeLuce').textContent = result.supplierName;
                recalculateLuce();
            } else {
                switchTab('gas');
                if (result.smc) document.getElementById('inputSmc').value = result.smc;
                if (result.totalAmount) document.getElementById('inputTotalGas').value = result.totalAmount;
                if (result.supplierName) document.getElementById('supplierBadgeGas').textContent = result.supplierName;
                recalculateGas();
            }
        } else {
            alert(result.error || "Impossibile estrarre i dati dalla bolletta.");
        }
    } catch (err) {
        overlay.classList.add('hidden');
        alert("Errore durante l'elaborazione del file: " + err.message);
    }
}

// Recalculate Electricity (Luce)
function recalculateLuce() {
    const kwh = parseFloat(document.getElementById('inputKwh').value) || 0;
    const totalCurrent = parseFloat(document.getElementById('inputTotalLuce').value) || 0;
    const months = parseInt(document.getElementById('inputMonthsLuce').value) || 2;
    const powerKw = parseFloat(document.getElementById('inputPowerKw').value) || 3.0;
    const utenza = document.getElementById('inputUtenzaLuce').value;

    const offerId = document.getElementById('selectOfferLuce').value;
    const targetOffer = catalogOffers.find(o => o.id === offerId) || catalogOffers[0];

    const isResidente = utenza === 'residente';
    const isBusiness = utenza === 'business';

    const targetParams = {
        kwh,
        months,
        powerKw,
        isResidente,
        isBusiness,
        tariffType: targetOffer.tariffType,
        fixedPriceKwh: targetOffer.fixedPriceKwh,
        spreadKwh: targetOffer.spreadKwh,
        punValue: targetOffer.punValue,
        pcvMonthly: targetOffer.pcvMonthly,
        discountMonthly: targetOffer.discountMonthly || 0
    };

    const comp = ARERA_ENGINE.compareOffers(totalCurrent, targetParams, 'LUCE');

    // UI Updates
    document.getElementById('valCurrentTotalLuce').textContent = comp.currentTotal.toFixed(2) + ' €';
    document.getElementById('valTargetTotalLuce').textContent = comp.targetTotal.toFixed(2) + ' €';
    document.getElementById('valKwhText').textContent = `${kwh} kWh (${months}m)`;
    
    const costPerKwhCurrent = kwh > 0 ? (totalCurrent / kwh) : 0;
    document.getElementById('valCostKwhCurrent').textContent = costPerKwhCurrent.toFixed(3) + ' €/kWh';

    document.getElementById('valTargetMateriaLuce').textContent = comp.calcTarget.spesaMateriaEnergia.toFixed(2) + ' €';
    document.getElementById('valTargetPcvLuce').textContent = (targetOffer.pcvMonthly - (targetOffer.discountMonthly||0)).toFixed(2) + ' €/m';

    const hero = document.getElementById('heroSavingsLuce');
    const valYearly = document.getElementById('valSavingsYearlyLuce');
    const valPeriod = document.getElementById('valSavingsPeriodLuce');

    if (comp.isPositive) {
        hero.className = 'savings-hero';
        valYearly.textContent = `+ ${comp.diffYearly.toFixed(2)} € / anno`;
        valPeriod.textContent = `Risparmio di ${comp.diffPeriod.toFixed(2)} € su questa bolletta (-${comp.savingsPercent}%)`;
    } else {
        hero.className = 'savings-hero negative';
        valYearly.textContent = `${comp.diffYearly.toFixed(2)} € / anno`;
        valPeriod.textContent = `L'offerta attuale risulta più economica di ${Math.abs(comp.diffPeriod).toFixed(2)} €`;
    }

    renderLuceChart(comp.calcTarget);
}

// Recalculate Gas
function recalculateGas() {
    const smc = parseFloat(document.getElementById('inputSmc').value) || 0;
    const totalCurrent = parseFloat(document.getElementById('inputTotalGas').value) || 0;
    const months = parseInt(document.getElementById('inputMonthsGas').value) || 2;

    const offerId = document.getElementById('selectOfferGas').value;
    const targetOffer = catalogOffers.find(o => o.id === offerId) || catalogOffers[2];

    const targetParams = {
        smc,
        months,
        isBusiness: false,
        tariffType: targetOffer.tariffType,
        fixedPriceSmc: targetOffer.fixedPriceSmc,
        spreadSmc: targetOffer.spreadSmc,
        psvValue: targetOffer.psvValue,
        qvdMonthly: targetOffer.qvdMonthly,
        discountMonthly: targetOffer.discountMonthly || 0
    };

    const comp = ARERA_ENGINE.compareOffers(totalCurrent, targetParams, 'GAS');

    // UI Updates
    document.getElementById('valCurrentTotalGas').textContent = comp.currentTotal.toFixed(2) + ' €';
    document.getElementById('valTargetTotalGas').textContent = comp.targetTotal.toFixed(2) + ' €';
    document.getElementById('valSmcText').textContent = `${smc} Smc (${months}m)`;
    
    const costPerSmcCurrent = smc > 0 ? (totalCurrent / smc) : 0;
    document.getElementById('valCostSmcCurrent').textContent = costPerSmcCurrent.toFixed(3) + ' €/Smc';

    document.getElementById('valTargetMateriaGas').textContent = comp.calcTarget.spesaMateriaGas.toFixed(2) + ' €';
    document.getElementById('valTargetQvdGas').textContent = (targetOffer.qvdMonthly - (targetOffer.discountMonthly||0)).toFixed(2) + ' €/m';

    const hero = document.getElementById('heroSavingsGas');
    const valYearly = document.getElementById('valSavingsYearlyGas');
    const valPeriod = document.getElementById('valSavingsPeriodGas');

    if (comp.isPositive) {
        hero.className = 'savings-hero';
        valYearly.textContent = `+ ${comp.diffYearly.toFixed(2)} € / anno`;
        valPeriod.textContent = `Risparmio di ${comp.diffPeriod.toFixed(2)} € su questa bolletta (-${comp.savingsPercent}%)`;
    } else {
        hero.className = 'savings-hero negative';
        valYearly.textContent = `${comp.diffYearly.toFixed(2)} € / anno`;
        valPeriod.textContent = `L'offerta attuale risulta più economica di ${Math.abs(comp.diffPeriod).toFixed(2)} €`;
    }

    renderGasChart(comp.calcTarget);
}

// Render Luce Chart.js
function renderLuceChart(targetData) {
    const ctx = document.getElementById('chartLuce').getContext('2d');
    if (chartLuceInstance) chartLuceInstance.destroy();

    chartLuceInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Materia Energia', 'Trasporto & Contatore', 'Oneri Sistema', 'Accise & IVA'],
            datasets: [{
                label: 'Costo Componenti Target (€)',
                data: [
                    targetData.spesaMateriaEnergia,
                    targetData.spesaTrasporto,
                    targetData.spesaOneri,
                    targetData.spesaAccise + targetData.spesaIva
                ],
                backgroundColor: ['#00f2fe', '#3b82f6', '#8b5cf6', '#10b981'],
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } }
            }
        }
    });
}

// Render Gas Chart.js
function renderGasChart(targetData) {
    const ctx = document.getElementById('chartGas').getContext('2d');
    if (chartGasInstance) chartGasInstance.destroy();

    chartGasInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Materia Gas', 'Trasporto & Contatore', 'Oneri Sistema', 'Accise & IVA'],
            datasets: [{
                label: 'Costo Componenti Target (€)',
                data: [
                    targetData.spesaMateriaGas,
                    targetData.spesaTrasporto,
                    targetData.spesaOneri,
                    targetData.spesaAccise + targetData.spesaIva
                ],
                backgroundColor: ['#ff9f43', '#f59e0b', '#ec4899', '#10b981'],
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } }
            }
        }
    });
}

// Render Catalog Offers in Tab 3
function renderCatalogList() {
    const container = document.getElementById('catalogOffersList');
    if (!container) return;

    container.innerHTML = catalogOffers.map(o => `
        <div class="comp-col" style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="font-weight: 700; font-size: 14px; color: ${o.type==='LUCE'?'var(--color-electric)':'var(--color-gas)'};">
                    ${o.name}
                </div>
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                    ${o.tariffType === 'FIXED' ? `Prezzo Fisso: ${o.fixedPriceKwh||o.fixedPriceSmc} €` : `Spread: +${o.spreadKwh||o.spreadSmc}`} 
                    | Quota Fissa: ${(o.pcvMonthly||o.qvdMonthly)}€/mese
                </div>
            </div>
            <button class="btn-preset" onclick="deleteOffer('${o.id}')"><i class="fa-solid fa-trash"></i></button>
        </div>
    `).join('');
}

function deleteOffer(id) {
    catalogOffers = catalogOffers.filter(o => o.id !== id);
    populateOfferSelectors();
    renderCatalogList();
    recalculateLuce();
    recalculateGas();
}

function showNewOfferModal() {
    const name = prompt("Nome della Nuova Offerta (es. Offerta Speciale 2026):");
    if (!name) return;
    const type = prompt("Tipologia ('LUCE' o 'GAS'):", "LUCE").toUpperCase();
    const price = parseFloat(prompt("Prezzo Fisso Materia Prima (€/kWh o €/Smc):", "0.110")) || 0.110;
    const pcv = parseFloat(prompt("Quota Fissa (€/mese PCV/QVD):", "8.0")) || 8.0;

    const newOffer = {
        id: 'custom_' + Date.now(),
        type: type === 'GAS' ? 'GAS' : 'LUCE',
        name: (type === 'GAS' ? '🔥 ' : '⚡ ') + name,
        tariffType: 'FIXED',
        fixedPriceKwh: price,
        fixedPriceSmc: price,
        pcvMonthly: pcv,
        qvdMonthly: pcv,
        discountMonthly: 0,
        description: 'Offerta personalizzata agenzia'
    };

    catalogOffers.push(newOffer);
    populateOfferSelectors();
    renderCatalogList();
    recalculateLuce();
    recalculateGas();
}

// Generate & Update Quote Sheet (Tab 4)
function generateQuotePDF(type) {
    switchTab('preventivo');
    updateQuoteSheet(type);
}

function updateQuoteSheet(serviceType = 'LUCE') {
    const isLuce = serviceType === 'LUCE';
    const amountYearly = isLuce ? document.getElementById('valSavingsYearlyLuce').textContent : document.getElementById('valSavingsYearlyGas').textContent;
    const subtext = isLuce ? document.getElementById('valSavingsPeriodLuce').textContent : document.getElementById('valSavingsPeriodGas').textContent;

    document.getElementById('quoteBigSavingsYearly').textContent = amountYearly;
    document.getElementById('quoteSubtext').textContent = subtext;
    document.getElementById('quoteMetaDate').textContent = "Data: " + new Date().toLocaleDateString('it-IT');
}

// Share Quote via WhatsApp
function shareWhatsAppQuote() {
    const clientName = document.getElementById('quoteClientName').value || "Cliente";
    const agentName = document.getElementById('quoteAgentName').value || "Venditore";
    const savingsText = document.getElementById('quoteBigSavingsYearly').textContent;

    const msg = `Ciao ${clientName}! 👋\n\nHo preparato la comparazione della tua bolletta su base normativa ARERA.\n\n` +
                `⭐ *Risparmio Annuo Garantito:* ${savingsText}\n\n` +
                `Con la nostra offerta manteniamo identiche le imposte e i costi di rete per legge, riducendo la tua spesa sulla materia prima e sulla quota fissa.\n\n` +
                `Cordiali saluti,\n*${agentName}*`;

    const encoded = encodeURIComponent(msg);
    window.open(`https://wa.me/?text=${encoded}`, '_blank');
}
