document.addEventListener('DOMContentLoaded', () => {
    const uploadBox = document.getElementById('uploadBox');
    const fileInput = document.getElementById('fileInput');
    const progressSection = document.getElementById('progressSection');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const resultSection = document.getElementById('resultSection');
    const resultContent = document.getElementById('resultContent');
    const errorSection = document.getElementById('errorSection');
    const errorText = document.getElementById('errorText');
    const turnstileWidget = document.getElementById('turnstileWidget');
    
    let turnstileToken = null;

    if (uploadBox && fileInput) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadBox.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            uploadBox.addEventListener(eventName, () => {
                uploadBox.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadBox.addEventListener(eventName, () => {
                uploadBox.classList.remove('drag-over');
            });
        });

        uploadBox.addEventListener('drop', handleDrop);
        uploadBox.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileSelect);
    }

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            processFile(files[0]);
        }
    }

    function handleFileSelect(e) {
        const files = e.target.files;
        if (files.length > 0) {
            processFile(files[0]);
        }
    }

    async function processFile(file) {
        hideAll();
        
        const maxSize = file.name.toLowerCase().endsWith('.zip') ? 50 * 1024 * 1024 : 10 * 1024 * 1024;
        if (file.size > maxSize) {
            showError(`File troppo grande. Massimo ${maxSize / (1024 * 1024)} MB.`);
            return;
        }

        if (turnstileWidget && window.turnstile) {
            progressSection.style.display = 'block';
            progressText.textContent = 'Verifica anti-bot in corso...';
            
            turnstileWidget.style.display = 'block';
            
            try {
                turnstileToken = await renderTurnstile();
            } catch (error) {
                showError('Verifica anti-bot fallita. Ricarica la pagina e riprova.');
                return;
            }
            
            turnstileWidget.style.display = 'none';
        }

        progressSection.style.display = 'block';
        progressText.textContent = 'Caricamento in corso...';
        progressFill.style.width = '30%';

        const formData = new FormData();
        formData.append('file', file);
        
        if (turnstileToken) {
            formData.append('turnstile_token', turnstileToken);
        }

        try {
            progressFill.style.width = '60%';
            progressText.textContent = 'Elaborazione in corso...';
            
            const response = await fetch('/api/process', {
                method: 'POST',
                body: formData
            });

            progressFill.style.width = '100%';

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Errore durante l\'elaborazione');
            }

            const data = await response.json();
            
            if (data.batch) {
                showBatchResult(data);
            } else {
                showSingleResult(data);
            }

        } catch (error) {
            showError(error.message);
        }
    }

    function showSingleResult(data) {
        hideAll();
        resultSection.style.display = 'block';
        
        let html = `
            <div class="result-info">
                <p><strong>File estratto:</strong> ${data.filename}</p>
                <p><strong>Tipo:</strong> ${data.mime_type}</p>
                <p><strong>Dimensione:</strong> ${formatBytes(data.size)}</p>
                <p><strong>SHA-256:</strong> <code style="font-size: 0.85em;">${data.sha256}</code></p>
            </div>
        `;
        
        if (data.signature) {
            const sig = data.signature;
            const statusIcon = sig.crypto_valid ? '✅' : sig.crypto_valid === false ? '❌' : '⚠️';
            const statusText = sig.crypto_valid ? 'Valida' : sig.crypto_valid === false ? 'Non valida' : 'Non verificata';
            
            html += `
                <div class="signature-info" style="margin-top: 1.5rem; padding: 1rem; background-color: #f8f9fa; border-radius: 6px;">
                    <h4>Firma Digitale ${statusIcon}</h4>
                    <p><strong>Stato:</strong> ${statusText}</p>
                    <p><strong>Firmatario:</strong> ${sig.signer_name}</p>
                    ${sig.organization ? `<p><strong>Organizzazione:</strong> ${sig.organization}</p>` : ''}
                    <p><strong>Valida dal:</strong> ${sig.valid_from} <strong>al:</strong> ${sig.valid_to}</p>
                    ${sig.is_expired ? '<p style="color: #C5504B;">⚠️ Certificato scaduto</p>' : ''}
                    <p><strong>Algoritmo:</strong> ${sig.algorithm}</p>
                    ${sig.validation_error ? `<p style="color: #C5504B;"><strong>Nota:</strong> ${sig.validation_error}</p>` : ''}
                </div>
            `;
        }
        
        if (data.fattura && data.download_id) {
            html += `
                <div style="margin-top: 1.5rem;">
                    <h4>Fattura Elettronica</h4>
                    <p>Questa è una fattura elettronica. Puoi scaricare:</p>
                    <div style="margin-top: 1rem; display: flex; gap: 1rem; flex-wrap: wrap;">
                        <a href="/api/download/pdf?download_id=${data.download_id}" 
                           class="btn btn-primary" 
                           download
                           style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #C5504B; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">
                            📄 Scarica PDF
                        </a>
                        <a href="/api/download/xml?download_id=${data.download_id}" 
                           class="btn btn-secondary" 
                           download
                           style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #6c757d; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">
                            📋 Scarica XML
                        </a>
                    </div>
                    <p style="margin-top: 1rem; font-size: 0.9em; color: #666;">
                        <em>Nota: Il PDF è un documento di cortesia senza valore fiscale. Il file con valore legale è l'XML.</em>
                    </p>
                </div>
            `;
        } else if (data.download_id) {
            html += `
                <div style="margin-top: 1.5rem;">
                    <h4>Download disponibili</h4>
                    <div style="margin-top: 1rem;">
                        <a href="/api/download/xml?download_id=${data.download_id}" 
                           class="btn btn-primary" 
                           download
                           style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #C5504B; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">
                            📋 Scarica file estratto
                        </a>
                    </div>
                </div>
            `;
        }
        
        resultContent.innerHTML = html;
    }

    function showBatchResult(data) {
        hideAll();
        resultSection.style.display = 'block';
        
        let html = `
            <div class="result-info">
                <p><strong>Batch completato!</strong></p>
                <p>File totali: ${data.total_files}</p>
                <p>Elaborati con successo: ${data.success_count}</p>
                <p>Fatture elettroniche trovate: ${data.fatture_count}</p>
            </div>
        `;
        
        if (data.fatture_count > 0 && data.download_id) {
            html += `
                <div style="margin-top: 1.5rem;">
                    <h4>Download disponibili</h4>
                    <p>Scarica un archivio ZIP contenente tutti i PDF delle fatture + un file Excel riepilogativo per il commercialista.</p>
                    <div style="margin-top: 1rem;">
                        <a href="/api/download/batch?download_id=${data.download_id}" 
                           class="btn btn-primary" 
                           download
                           style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #C5504B; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">
                            📦 Scarica ZIP (PDF + Excel)
                        </a>
                    </div>
                    <p style="margin-top: 1rem; font-size: 0.9em; color: #666;">
                        <em>Il file Excel contiene un riepilogo delle fatture con importi e aliquote IVA.</em>
                    </p>
                </div>
            `;
        }
        
        if (data.results && data.results.length > 0) {
            html += '<div style="margin-top: 1.5rem;"><h4>Dettaglio file:</h4><ul>';
            data.results.slice(0, 10).forEach(result => {
                if (result.success) {
                    html += `<li>✅ ${result.filename} → ${result.extracted_filename}</li>`;
                } else {
                    html += `<li>❌ ${result.filename}: ${result.error}</li>`;
                }
            });
            if (data.results.length > 10) {
                html += `<li><em>... e altri ${data.results.length - 10} file</em></li>`;
            }
            html += '</ul></div>';
        }
        
        resultContent.innerHTML = html;
    }

    function showError(message) {
        hideAll();
        errorSection.style.display = 'block';
        errorText.textContent = message;
    }

    function hideAll() {
        progressSection.style.display = 'none';
        resultSection.style.display = 'none';
        errorSection.style.display = 'none';
        progressFill.style.width = '0%';
    }

    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    function renderTurnstile() {
        return new Promise((resolve, reject) => {
            const siteKey = turnstileWidget.dataset.sitekey;
            
            window.turnstile.render('#turnstileWidget', {
                sitekey: siteKey,
                callback: (token) => {
                    resolve(token);
                },
                'error-callback': () => {
                    reject(new Error('Turnstile verification failed'));
                }
            });
        });
    }
});
