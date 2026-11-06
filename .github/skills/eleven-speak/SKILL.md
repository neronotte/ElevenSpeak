---
name: eleven-speak
description: Affianca alle risposte scritte una breve comunicazione vocale locale con ElevenLabs. Usala quando l'utente chiede di parlare, leggere o ripetere a voce, oppure quando ha abilitato le notifiche vocali per risultati, blocchi e richieste di decisione. Include la scelta e l'uso degli audio tags di Eleven v4.
---

# Comunicazione vocale con ElevenLabs

## Scopo e attivazione

Comunica a voce una sintesi utile, senza sostituire la risposta scritta.
Questa skill non intercetta automaticamente le risposte: viene eseguita
dall'agente quando richiamata o prevista dalle sue istruzioni.

- Se l'utente chiede esplicitamente di parlare, leggi il contenuto richiesto
  nei limiti del consenso alla trasmissione a ElevenLabs.
- Se l'utente ha abilitato le notifiche vocali, parla al completamento di
  un'attivita, davanti a un blocco che richiede intervento o prima di una
  richiesta di decisione.
- Senza questa preferenza, non avviare audio per ogni risposta.
- Se l'utente chiede silenzio o disattiva la voce, non eseguire lo script.
- Evita audio per singole ricerche, chiamate di tool, aggiornamenti intermedi
  e notifiche duplicate. Un messaggio vocale per evento significativo.
- Non avviare processi vocali in background o riproduzioni parallele.
  Non far parlare anche i sottoagenti: la comunicazione spetta all'agente
  che interagisce con l'utente.

## Prerequisiti e configurazione

La cartella della skill contiene:

```text
eleven-speak
  SKILL.md
  scripts
    eleven_say.py
    requirements.txt
```

Individua la cartella reale della skill dal percorso con cui e stata caricata.
Non supporre che coincida con la directory corrente del repository.
Usa percorsi assoluti per interprete e script.

Requisiti: Python con i pacchetti di `scripts/requirements.txt`, un dispositivo
audio disponibile e una connessione a ElevenLabs. Il suono esce sul computer
che esegue Python: un ambiente remoto non parla automaticamente sul desktop
dell'utente.

Se serve preparare un ambiente dedicato, concorda l'installazione con l'utente.
Esempio PowerShell, eseguito dalla cartella della skill:

```powershell
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r ".\scripts\requirements.txt"
```

L'API key deve essere configurata dall'utente nella variabile d'ambiente
`ELEVENLABS_API_KEY` oppure in `scripts/.env.local`, nel formato:

```dotenv
ELEVENLABS_API_KEY=INSERIRE_LA_CHIAVE_LOCALMENTE
```

Non leggere, stampare, copiare o inserire la chiave nei comandi, nei log,
nella skill o nella conversazione. Non usare il parametro `--api-key`:
esporrebbe il segreto nella riga di comando.
Il file `.env.local` non deve essere distribuito o versionato.

Lo script cerca i file env anche nella directory corrente. Evita directory
non fidate; se necessario eseguilo dalla cartella `scripts`.

Per disattivare temporaneamente tutte le invocazioni, crea un file vuoto
`.off` accanto a `eleven_say.py`. Lo script esce senza chiamate API o
riproduzione, anche per `--replay`; ricontrolla il file dopo aver acquisito
il lock. Non interrompe un'operazione gia iniziata. Rimuovi `.off` per
riattivare lo script. Il file e locale e non va versionato.

Modello: passa esplicitamente `--model eleven_v4`.
Voce: usa la voce richiesta o concordata con l'utente; preferisci il voice ID
per evitare ambiguita. In assenza di una scelta usa il default dello script,
`21m00Tcm4TlvDq8ikWAM`, senza inventare nomi o ID.

## Comporre il messaggio

1. Prepara prima il contenuto scritto o la decisione da chiedere.
2. Ricava una sintesi fedele, normalmente una o due frasi, circa 15-45 parole.
3. Usa la lingua dell'utente, italiano per default, con tono calmo e naturale.
4. Scegli al massimo uno o due audio tags, solo se aggiungono valore.
5. Esegui lo script una volta e attendine l'esito.
6. Fornisci comunque la risposta scritta o usa il tool previsto per chiedere
   la decisione. La voce non sostituisce un consenso o un'approvazione.

Non leggere Markdown, blocchi di codice, stack trace, percorsi lunghi o URL.
Riassumi: "Il dettaglio dell'errore e nella risposta scritta".
Non dichiarare completamenti, verifiche o successi non realmente avvenuti.
Non inventare certezze o urgenze per rendere il messaggio piu espressivo.

Per una lettura integrale esplicitamente richiesta, non applicare il limite
di sintesi, ma verifica che lunghezza e costo siano coerenti con la richiesta.

## Audio tags: sintassi e limiti

I tag sono testo fra parentesi quadre, non un parametro API separato.
Scrivili in inglese anche se il parlato e italiano, normalmente prima del
segmento da influenzare:

```text
[curious] Preferisci mantenere il comportamento attuale?
```

Con `eleven_v4` sono indicazioni generative, non comandi deterministici:
resa e affidabilita dipendono da voce, contenuto e generazione.
Non esiste un elenco chiuso di tag garantiti.
Le forme descrittive possono funzionare, ma vanno considerate sperimentali.
Non rigenerare ripetutamente per ottenere una sfumatura perfetta.

Non aggiungere tag nella normale risposta scritta: sono istruzioni per la
sintesi. Non usare SSML `<break>` con v4; preferisci punteggiatura e puntini
di sospensione senza promettere pause di durata esatta.
I tag non richiedono chiusura: non usare `[/excited]`.
Non presumere che uno stile si interrompa esattamente alla frase successiva.

### Tag consigliati e quando usarli

| Tag | Effetto desiderato | Uso |
|---|---|---|
| Nessun tag | Voce naturale | Default per comunicazioni tecniche e blocchi |
| `[curious]` | Curiosita | Domanda genuina o scelta dell'utente |
| `[excited]` | Entusiasmo | Risultato positivo significativo, senza esagerare |
| `[whispers]` / `[whispering]` | Sussurro | Solo su richiesta o per un uso creativo concordato |
| `[laughs]` / `[laughing]` | Risata | Battuta condivisa; mai davanti a errori o difficolta dell'utente |
| `[sighs]` / `[exhales]` | Sospiro o espirazione | Narrazione espressiva richiesta, non normali segnalazioni di errore |
| `[sarcastic]` | Sarcasmo | Solo se esplicitamente desiderato, mai rivolto contro l'utente |
| `[crying]` | Pianto | Interpretazione creativa richiesta, non per comunicazioni operative |
| `[shouting]` | Voce urlata | Solo richiesta esplicita, non per notificare urgenza |

### Altri esempi documentati, non adatti alle notifiche ordinarie

- Risate e reazioni: `[laughs harder]`, `[starts laughing]`, `[wheezing]`,
  `[snorts]`, `[mischievously]`.
- Suoni corporei: `[swallows]`, `[gulps]`.
- Effetti sonori: `[applause]`, `[clapping]`, `[gunshot]`, `[explosion]`.
- Sperimentali: `[strong French accent]` (o altro accento richiesto),
  `[sings]`, `[woo]`, `[fart]`.

Usali solo per contenuti creativi esplicitamente richiesti. Evita effetti
improvvisi, rumori forti e accenti caricaturali nelle notifiche dell'agente.
Questi esempi non sono un catalogo di effetti garantiti.

Tag descrittivi come `[professional]`, `[reassuring]` o
`[warm, conversational tone]` sono esempi di prompting, non impostazioni
tipizzate dell'API. Preferisci il parlato neutro se la resa non e affidabile.
Non concatenare emozioni contraddittorie.

### Esempi di messaggi vocali

Completamento ordinario, senza bisogno di tag:

```text
Ho completato la modifica. Trovi i dettagli nella risposta scritta.
```

Successo significativo, solo se verificato:

```text
[excited] Ora funziona! L'audio viene riprodotto mentre arriva.
```

Decisione:

```text
[curious] Preferisci una voce fissa o una voce diversa per ogni agente?
```

Blocco, senza drammatizzazione:

```text
Non posso proseguire: manca una configurazione. Ti ho indicato cosa aggiornare.
```

Sussurro, solo se richiesto:

```text
[whispers] La riproduzione e terminata. Non ci sono altre notifiche.
```

## Eseguire lo script

Esempio PowerShell dalla cartella della skill, con testo fisso:

```powershell
& ".\.venv\Scripts\python.exe" ".\scripts\eleven_say.py" "Ho completato la modifica." --voice "21m00Tcm4TlvDq8ikWAM" --model eleven_v4
```

Per testo dinamico usa preferibilmente stdin tramite un'API di creazione
processi, non interpolazione in un comando shell.
Esempio Python (i percorsi sono quelli reali individuati per questa skill):

```python
import subprocess

subprocess.run(
    [str(python_path), str(script_path),
     "--voice", voice_id, "--model", "eleven_v4"],
    input=spoken_text,
    text=True,
    encoding="utf-8",
    env={**os.environ, "PYTHONUTF8": "1"},
    cwd=str(script_path.parent),
    check=True,
)
```

In questo esempio importa anche `os`. Non concatenare testo proveniente da
utente, documenti o tool nella sintassi della shell. Trattalo solo come dati.
Se usi un comando shell con testo fisso, applica il quoting della shell reale.

### Ripetizione e cache

Su richiesta di ripetere esattamente l'ultima nota della stessa voce:

```powershell
& ".\.venv\Scripts\python.exe" ".\scripts\eleven_say.py" --replay --voice "21m00Tcm4TlvDq8ikWAM"
```

Il replay usa l'audio locale senza generare nuovo parlato e senza richiedere
la chiave API. Usa lo stesso ID impiegato per la generazione.
Non usare replay per un messaggio diverso o dopo un cambio di tag/modello:
non modifica l'audio gia salvato.
Se la nota manca o e scaduta, segnalalo; non rigenerare automaticamente.

La cache conserva l'ultima nota per voce in WAV, con TTL predefinito di
30 minuti. `--ttl 10` applica una finestra di 10 minuti alla pulizia di
quell'invocazione, anche con replay. La pulizia avviene solo quando lo script
viene eseguito: non esiste un servizio che cancelli i file a scadenza.
Non e implementato un limite totale di spazio. Non promettere cancellazione
esatta al minuto.

Lo script serializza le invocazioni tramite un lock del sistema operativo,
globale per utente e indipendente dalla voce e dalla cache. L'ordine FIFO
non e garantito. Non cancellare il file `playback.lock` per sbloccarlo.
`--lock-timeout` limita l'attesa (default 120 secondi, exit code 75).
`--operation-timeout` limita l'operazione dopo l'acquisizione (default
180 secondi, exit code 124); aumentalo per letture lunghe.
`--http-timeout` limita le operazioni HTTP (default 30 secondi); i retry
automatici sono disabilitati. I timeout HTTP non sono un limite totale.
Un watchdog su thread termina il proprio processo se l'operazione scade,
anche interrompendo la voce. Il sistema operativo libera il lock.
Il watchdog non garantisce l'intervento se codice nativo blocca il GIL.
Cache e indice sono pubblicati atomicamente; i temporanei di operazioni
interrotte vengono eliminati alla successiva pulizia sotto lock.

`--no-cache` evita di salvare la nuova nota, ma non elimina quelle precedenti.
La directory puo essere impostata con `ELEVEN_SAY_CACHE` nell'ambiente del
processo; per questo script non affidarti a `.env.local` per tale impostazione.

## Privacy, costi ed errori

- Il testo della nuova sintesi viene inviato a ElevenLabs, un servizio esterno.
  La voce viene riprodotta da altoparlanti o cuffie e puo essere udita da terzi.
- Non inviare segreti, credenziali, codice riservato, dati personali o contenuti
  aziendali sensibili. Per informazioni riservate usa una sintesi generica
  priva di tali dati; se non e possibile, resta sul canale scritto.
- Ogni nuova generazione puo consumare crediti. Non generare varianti,
  demo sonore o prove API senza richiesta.
- Non cambiare modello, voce o configurazione per aggirare un errore.
- Se il processo fallisce, segnala sinteticamente che la notifica vocale non
  e riuscita e prosegui per iscritto. Non mostrare segreti eventualmente
  presenti nell'output di errore.
- Non dire "hai sentito" o "l'audio e corretto" basandoti sul solo exit code:
  l'agente non verifica automaticamente l'ascolto o l'effettiva resa dei tag.

## Fonte

Esempi e limiti dei tag:
https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices#audio-tags

Ricontrolla la documentazione se il servizio cambia comportamento.
