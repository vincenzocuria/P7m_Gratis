import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

const appVersion = '1.2.0 (7)';
const privacyUrl = 'https://vincenzocuria.github.io/P7m_Gratis/privacy.html';
const supportEmail = 'support@vcuria.app';

class HelpPage extends StatelessWidget {
  const HelpPage({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Come funziona')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: const [
        _HelpCard(
          Icons.folder_open,
          '1. Apri un documento',
          'Scegli Apri un P7M o PDF. Puoi anche usare Apri con o Condividi da email, chat e gestore file. Limite: 50 MB.',
        ),
        _HelpCard(
          Icons.description_outlined,
          '2. Leggi ed esporta',
          'Il tipo è sempre indicato: PDF semplice oppure documento estratto da P7M. Tocca il nome per leggerlo completo. Nei PDF usa due dita per ingrandire e scorri per cambiare pagina. Salva crea una copia; Condividi la invia all’app che scegli.',
        ),
        _HelpCard(
          Icons.verified_user_outlined,
          '3. Comprendi le firme',
          'La scheda Firme compare per i P7M. Integrità indica se il contenuto corrisponde alla firma; il certificato viene controllato con le radici del telefono. Non accertata significa che mancano elementi per concludere: non equivale automaticamente a una firma falsa.',
        ),
        _HelpCard(
          Icons.wifi,
          '4. Revoca online, solo se vuoi',
          'Controlla revoca online contatta gli emittenti con IP e identificativo del certificato, senza inviare il documento. Alcuni servizi usano HTTP. Il simbolo positivo richiede integrità, catena attendibile e revoca accertate.',
        ),
        _HelpCard(
          Icons.info_outline,
          'Cosa non viene certificato',
          'Le firme interne ai PDF (PAdES) non vengono verificate. Qualificazione eIDAS e validità storica complessiva non sono accertate. Per decisioni con effetti legali usa anche un servizio di validazione appropriato.',
        ),
        _HelpCard(
          Icons.cleaning_services_outlined,
          'I tuoi file restano tuoi',
          'Da ? puoi chiudere il documento e pulire le copie temporanee. Gli originali e i file che hai salvato non vengono eliminati. Privacy e guida sono disponibili anche senza connessione.',
        ),
      ],
    ),
  );
}

class _HelpCard extends StatelessWidget {
  const _HelpCard(this.icon, this.title, this.text);
  final IconData icon;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: Theme.of(context).colorScheme.primary),
          const SizedBox(height: 12),
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(text),
        ],
      ),
    ),
  );
}

class PrivacyPage extends StatelessWidget {
  const PrivacyPage({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Privacy')),
    body: FutureBuilder<String>(
      future: rootBundle.loadString('assets/privacy.txt'),
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return const Center(child: Text('Informativa non disponibile'));
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        return SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: SelectableText(snapshot.data!),
        );
      },
    ),
  );
}
