# P7M Viewer 1.3.4 (13)

- Esportazione locale di una nuova copia PDF senza password, con dichiarazione esplicita di autorizzazione e avvisi su riservatezza e firme. L’originale viene conservato.
- Verifica automatica della copia: riapertura senza password e controllo del numero di pagine.
- Errori del lettore PDF in italiano e pulsante Riprova.
- Nei PDF cifrati le firme interne sono indicate come non accertate.
- Riconoscimento Android delle estensioni P7S/TSD/M7M e messaggi specifici per firme separate o contenitori temporali non supportati. Non equivale al supporto completo TSD/M7M.

## Correzioni della 1.3.3 incluse

- PDF protetti: richiesta della password, possibilità di riprovare se errata e annullamento.
- Salva e Condividi: scelta tra originale firmato P7M, identico al file ricevuto, e documento estratto senza la busta P7M.
- Conservazione dell'originale anche per allegati aperti da altre app e buste annidate.

Verifica: suite Flutter e motore PDF nativo con campioni sintetici RC4/AES, anche dentro P7M. Prova manuale su Android ancora da eseguire. Il testo legale richiede revisione professionale prima di essere presentato come validato.
