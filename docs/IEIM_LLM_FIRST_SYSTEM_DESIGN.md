# IEIM — System Design: LLM‑First Mode mit Toggle zum Baseline‑Modus (Fail‑Closed, Auditierbar, Reproduzierbar)

**Zielgruppe:** Codex / Engineering Team  
**Kontext:** IEIM hat eine bestehende Baseline‑Pipeline (deterministische Regeln → leichtgewichtiges deterministisches Modell → optional LLM gated).  
**Neue Anforderung:** Eine **LLM‑first** Variante, die bei unstrukturierten E‑Mails weniger manuelle Reviews benötigt, aber weiterhin rechtssicher, auditierbar und fail‑closed bleibt.  
**Wichtig:** Ich habe keinen Zugriff auf Repo‑Dateien. Die folgenden Festlegungen sind so formuliert, dass Codex ohne Erfinden implementieren kann.

---

## 1) Ziele und Begründung

### 1.1 Ziele (messbar)
1. **Reduktion manuelle Reviews** für unstrukturierte E‑Mails, indem Intent/Produkt/Urgency/Entities robuster erkannt werden.  
2. **Keine Verschlechterung kritischer Sicherheits‑ und Compliance‑Eigenschaften**:
   - Fail‑closed bei Unsicherheit
   - Immutability für Raw + Audit
   - Determinismus‑Modus reproduzierbar (Decision‑Hashes ohne Timestamps)
   - Audit Events je Stage mit Hashes, Versionen, Evidence‑Spans
3. **Rechtssicherer Betrieb**:
   - Nachvollziehbarkeit jeder Entscheidung (wer/was/wieso)
   - Keine autonomen Antworten; Drafts stets approval‑gated

### 1.2 Warum LLM‑first
Unstrukturierte E‑Mails enthalten Tippfehler, Umgangssprache, gemischte Themen und fehlende Referenzen. Deterministische Regeln und kleine Modelle sind hier häufig zu unsicher. Ein LLM kann:
- Intents besser aus Kontext ableiten (auch bei Rechtschreibfehlern)
- Produktlinie trotz impliziter Hinweise erkennen
- Entities extrahieren, auch wenn Format variabel ist

**Sicherheitsprinzip:** LLM‑first bedeutet nicht blindes Vertrauen. LLM‑Output wird nur akzeptiert, wenn er strenge Validierungs‑ und Konsistenz‑Gates besteht. Sonst Review/Request‑Info.

---

## 2) Pipeline‑Design für beide Modi

### 2.1 Gemeinsame, unveränderliche Stages (SSOT‑konform)
Pipeline bleibt strukturell wie bestehend:

1. Ingest  
2. Normalize  
3. Attachments  
4. Identity  
5. Classification  
6. Extraction  
7. Routing  
8. Case/Review  
Audit an jedem Schritt

**Keine neuen Stage‑IDs werden eingeführt.** Sub‑Schritte werden als Teil einer Stage umgesetzt (und separat als AuditEvents protokolliert).

### 2.2 Baseline‑Modus (unverändert)
**Zweck:** Maximum Determinismus, konservativ, LLM optional.

- **Identity:** deterministisches Scoring aus Signals (Header, Body, Attachments OCR, Directory Lookup falls vorhanden)  
- **Classification:**  
  1) deterministische Regeln  
  2) leichtgewichtiges deterministisches Modell  
  3) optional LLM gated (default aus)  
- **Extraction:** deterministische Extraktion + optional LLM gated (default aus)  
- **Routing:** deterministische Decision Tables + harte Risk Overrides

### 2.3 LLM‑First Modus (empfohlenes Design)
**Zweck:** LLM ist primärer Entscheider für Classification und Extraction, während deterministische Checks als Safety‑Net und Gate dienen.

**LLM‑first Stage‑Logik:**

**Identity Stage (weiterhin deterministisch als Final Authority)**
- Deterministische Signalextraktion (Regex, Header, OCR‑Text)
- Optionaler LLM‑Assist innerhalb der Identity Stage:
  - LLM liefert zusätzliche Kandidaten‑Signale (z. B. mögliche Polizzennummer aus Tippfehlern)
  - Diese Signale werden nur verwendet, wenn sie deterministisch validiert werden (Pattern‑Check plus Directory‑Existenzcheck)
- Final Identity Score bleibt deterministisch

**Classification Stage (LLM primär, Regeln/kleines Modell als Gate)**
- Deterministischer Risk Pre‑Scan läuft immer (siehe Abschnitt 3.1)
- LLM erzeugt ClassificationResult (strict JSON, canonical labels)
- Leichtgewichtiges Modell läuft parallel als Plausibilitätscheck, nicht als Final Authority
- Disagreement‑Gate entscheidet: akzeptieren oder Review

**Extraction Stage (LLM primär, deterministische Validierung)**
- LLM erzeugt ExtractionResult (strict JSON, Entities mit Evidence‑Spans)
- Deterministische Validatoren prüfen:
  - Syntax und Pattern der Entities (Polizzen, Claim, IBAN falls erlaubt)
  - Evidence‑Span Range und Hash‑Match
- Wenn Entities für Identity kritisch sind und unsicher: Request‑Info oder Identity Review

**Routing Stage**
- Routing bleibt deterministisch
- Risk Overrides werden hart und zuerst angewendet (siehe Canonical Overrides)

---

## 3) LLM‑Gating und Akzeptanzregeln

### 3.1 Harte Sicherheits‑ und Risk‑Regeln (immer, vor LLM‑Akzeptanz)
Die folgenden Overrides werden **immer** angewendet und haben Vorrang vor jedem LLM‑Output:

- `RISK_SECURITY_MALWARE` → `QUEUE_SECURITY_REVIEW`, `SLA_1H`, `BLOCK_CASE_CREATE`
- `RISK_REGULATORY` → `QUEUE_COMPLAINTS`, `SLA_1H`
- `RISK_LEGAL_THREAT` → `QUEUE_LEGAL`, `SLA_1H`
- `RISK_FRAUD_SIGNAL` → `QUEUE_FRAUD`, `SLA_4H`
- `RISK_LANGUAGE_UNSUPPORTED` → `QUEUE_INTAKE_REVIEW_GENERAL`, `SLA_1BD`
- `RISK_SELF_HARM_THREAT` → `QUEUE_INTAKE_REVIEW_GENERAL`, `SLA_1H` plus Eskalationshinweis (als Audit Note, kein neuer Label)

**Deterministische Risk‑Erkennung (Pflicht):**
- Malware Risk kommt aus AV/OCR Pipeline und Attachment Status
- Legal / Regulatory / Fraud / Self‑harm / Autoreply Loop werden deterministisch per Keyword‑Ruleset erkannt
- LLM darf Risk Flags ergänzen, aber nicht entfernen
- Wenn LLM Risk Flags setzt, müssen Confidence und Evidence‑Spans vorhanden sein

### 3.2 LLM Output Acceptance (Classification)
LLM‑Classification wird nur akzeptiert, wenn alle Bedingungen erfüllt sind:

1. **Strict JSON**: Output parst als JSON und validiert gegen bestehendes ClassificationResult Schema.  
2. **Canonical Labels**:  
   - Intents müssen exakt aus dem kanonischen Set stammen  
   - Produktlinie exakt aus dem kanonischen Set  
   - Urgency exakt aus dem kanonischen Set  
   - Risk Flags exakt aus dem kanonischen Set  
3. **Confidence Gate (konfigurierbar, Empfehlung):**
   - `primary_intent.confidence >= 0.72`
   - `product_line.confidence >= 0.65`
   - `urgency.confidence >= 0.60`
   - Jeder gesetzte Risk Flag: `confidence >= 0.80`
4. **Evidence Gate:**
   - Für `primary_intent`, `product_line`, `urgency` mindestens je 1 Evidence‑Span
   - Evidence‑Spans referenzieren canonicalized body oder attachment_text
   - Start/End liegen innerhalb der Textlänge, snippet_hash passt
5. **Disagreement Gate (mit deterministischer Gegenprüfung):**
   - Wenn deterministische Regeln mit hoher Sicherheit einen anderen Intent ergeben, dann Review
   - Konkrete Regel: Wenn Rule Engine einen Intent mit `rule_confidence >= 0.85` produziert und der LLM primary_intent ist verschieden, dann `QUEUE_CLASSIFICATION_REVIEW`
6. **Refusal/Unsafe Gate:**
   - Wenn LLM Output verweigert oder nicht‑konform ist, dann fail‑closed zu Review

**Fail‑Closed Result:**  
Wenn irgendeine Bedingung nicht erfüllt ist, setze Routing so, dass ein Review erzwungen wird: `QUEUE_CLASSIFICATION_REVIEW` mit Actions `ATTACH_ORIGINAL_EMAIL`, `ATTACH_ALL_FILES`. Optional `ADD_REQUEST_INFO_DRAFT` wenn fehlende Mindestinfos erkennbar sind.

### 3.3 LLM Output Acceptance (Extraction)
LLM‑Extraction wird nur akzeptiert, wenn alle Bedingungen erfüllt sind:

1. **Strict JSON**: Output validiert gegen bestehendes ExtractionResult Schema.  
2. **Entity Types**: Nur kanonische Entity Types, keine freien Strings.  
3. **Entity Confidence Gate (konfigurierbar, Empfehlung):**
   - `ENT_POLICY_NUMBER` und `ENT_CLAIM_NUMBER`: `confidence >= 0.85`
   - Andere Entities: `confidence >= 0.70`
4. **Deterministische Pattern‑Validierung:**
   - Policy/Claim Nummern müssen Pattern‑valid sein (Regex im Code)
   - Wenn Pattern‑valid aber Directory Lookup ergibt keine Existenz: markiere als unsicher und triggert Identity Review
5. **Evidence Gate:** Jede Entity muss mindestens einen Evidence‑Span haben, der verifizierbar ist

**Fail‑Closed Result:**  
Wenn Extraktion scheitert oder unsicher ist, bleiben Stage Outputs vorhanden, aber Routing muss Review erzwingen:
- wenn identity‑kritisch: `QUEUE_IDENTITY_REVIEW` plus `ADD_REQUEST_INFO_DRAFT`
- wenn nur ergänzend: `QUEUE_INTAKE_REVIEW_GENERAL`

---

## 4) Determinismus und Reproduzierbarkeit

### 4.1 Grundsatz
- Decision Hashes sind timestamp‑frei
- Canonicalization ist deterministisch (HTML stripping, whitespace normalization, stable ordering)
- Audit Logs sind append‑only, Hash‑Chain verifizierbar

### 4.2 LLM Determinismus in der Praxis
LLMs sind in der Realität nicht garantiert bit‑identisch reproduzierbar, auch bei `temperature=0`. Daher wird für IEIM folgender Mechanismus empfohlen:

**Empfehlung: Reproduzierbarkeit durch Immutable LLM Inference Artifacts + Cache**
- Jeder LLM Call produziert ein **immutable Inference Artifact** (InputDigest, PromptHash, ModelId, Params, OutputJSON, OutputHash).
- Für Reprocessing wird dieses Artifact wiederverwendet, nicht neu inferiert, wenn `determinism_mode=true`.

**Determinism‑Modus Regel (fail‑closed):**
- Wenn `determinism_mode=true` und kein passendes LLM Inference Artifact vorhanden ist, wird **kein Live‑LLM Call** ausgeführt.  
- Stattdessen: fail‑closed zu Review (`QUEUE_CLASSIFICATION_REVIEW`) und AuditEvent mit Grund.

Das ist die einzig robuste Methode, um die Forderung „Input+Config reproduzierbar“ praktisch zu erfüllen.

### 4.3 Cache Key (deterministisch)
`llm_cache_key = sha256( RFC8785_JSON( { purpose, model_id, model_params, prompt_sha256, input_digest_sha256 } ) )`

- `purpose` ist z. B. `"CLASSIFY"` oder `"EXTRACT"` oder `"IDENTITY_ASSIST"`
- `model_params` enthält nur deterministische Parameter: temperature, top_p, max_tokens
- Keine timestamps, keine run_id, keine random seeds im Key

### 4.4 Deterministische Retries
Retries sind erlaubt, aber deterministisch definiert:

- Maximal 2 Versuche:
  1) Primary Prompt
  2) Repair Prompt (nur wenn JSON invalid, gleiche Labels, gleiche constraints)
- Beide Prompts sind versioniert, PromptHash wird geloggt
- Wenn Versuch 2 scheitert: fail‑closed

---

## 5) Audit Events pro Stage inklusive LLM

### 5.1 Audit Mindestanforderungen (pro Stage)
Jede Stage emittiert mindestens einen AuditEvent, der enthält:
- input_ref (artifact ref)
- output_ref (artifact ref)
- stage id
- decision_hash
- config hash und rules version
- evidence spans (redacted snippets plus snippet hash)
- model/prompt versions wenn model beteiligt

### 5.2 LLM Audit (innerhalb der Stage)
Wenn LLM genutzt wird, emittiere zusätzlich einen AuditEvent für die LLM Inference:

- stage bleibt `CLASSIFY` oder `EXTRACT` oder `IDENTITY`
- output_ref zeigt auf das LLM Inference Artifact
- model_info enthält:
  - provider (local oder external)
  - model_id (string)
  - prompt_sha256 und prompt_version
  - token usage (input_tokens, output_tokens) falls verfügbar
- evidence:
  - referenziert die Textbereiche, die im Prompt enthalten waren (canonicalized sections)

**Canonical Update erforderlich:** Falls das bestehende Schema für AuditEvent kein Feld für token usage oder prompt hashes hat, muss das AuditEvent Schema erweitert werden. Wenn es bereits existiert, wird es genutzt und nicht geändert.

---

## 6) Konfiguration und Toggle (Flags, sichere Defaults)

### 6.1 Empfohlene Defaults (enterprise‑safe)
- Default bleibt Baseline‑Modus.
- LLM‑first ist explizit zu aktivieren.

### 6.2 Konfig Flags (exakt, implementierbar)

**Canonical Update erforderlich:** Diese Schlüssel sollten als kanonische Config Keys in `spec/00_CANONICAL.md` aufgenommen werden, damit SSOT gewahrt bleibt.

- `pipeline.mode`  
  - allowed: `BASELINE` oder `LLM_FIRST`  
  - default: `BASELINE`

- `llm.enabled`  
  - allowed: `true` oder `false`  
  - default: `false`

- `llm.provider`  
  - allowed: `LOCAL` oder `EXTERNAL`  
  - default: `LOCAL`  
  - EXTERNAL darf nur aktiv sein, wenn ein expliziter Privacy‑Policy Flag gesetzt ist

- `llm.external.allowed`  
  - allowed: `true` oder `false`  
  - default: `false`

- `llm.purposes.enabled`  
  - list subset of: `IDENTITY_ASSIST`, `CLASSIFY`, `EXTRACT`  
  - default im Baseline: leere Liste  
  - default im LLM_FIRST: `CLASSIFY`, `EXTRACT`, optional `IDENTITY_ASSIST` je nach Privacy

- `llm.thresholds.classification.primary_intent_min` default 0.72  
- `llm.thresholds.classification.product_line_min` default 0.65  
- `llm.thresholds.classification.urgency_min` default 0.60  
- `llm.thresholds.classification.risk_flag_min` default 0.80  
- `llm.thresholds.extraction.high_value_entity_min` default 0.85  
- `llm.thresholds.extraction.other_entity_min` default 0.70

- `determinism_mode`  
  - allowed: `true` oder `false`  
  - wenn true und LLM needed aber cache miss: fail‑closed

- `privacy.external_llm_policy`  
  - allowed: `DENY_ALL` oder `ALLOW_CLASSIFICATION_ONLY_REDACTED`  
  - default: `DENY_ALL`

### 6.3 Provider Policy (empfohlen)
- LOCAL ist Standard und wird für sensitive Inhalte verwendet.
- EXTERNAL ist nur erlaubt, wenn:
  - `privacy.external_llm_policy = ALLOW_CLASSIFICATION_ONLY_REDACTED`
  - Keine der folgenden Risk Flags aktiv ist:  
    `RISK_PRIVACY_SENSITIVE`, `RISK_LEGAL_THREAT`, `RISK_REGULATORY`, `RISK_SECURITY_MALWARE`
  - EXTERNAL wird nur für `CLASSIFY` verwendet, nicht für `EXTRACT` und nicht für `IDENTITY_ASSIST`

---

## 7) Schema und Contract Auswirkungen

### 7.1 Keine neuen Labels oder Queues
Die Ausgabe nutzt ausschließlich die genannten kanonischen Labels, Queues und Actions.

### 7.2 Neue Artifacts für LLM Inference (empfohlen)
Für saubere Reproduzierbarkeit und Audit wird ein eigenes Artifact Schema empfohlen.

**Canonical Update erforderlich:**
- Neues Schema: `urn:ieim:schema:llm-inference:1.0.0`
- Neue Datei in `schemas/`: `llm_inference.schema.json`
- Update `spec/00_CANONICAL.md` um Schema ID und Version

Wenn ein neues Schema nicht eingeführt werden darf, kann das Inference Artifact als JSON ohne Schema gespeichert werden. Dann muss jedoch die Pack‑Validierung explizit diese Artefaktklasse erlauben. Das ist weniger drift‑proof.

---

## 8) Betrieb (Kosten, Latenz, Rate‑Limits, Privacy, extern vs lokal)

### 8.1 Kostenkontrolle
- Token Budgets pro Purpose:
  - CLASSIFY: input_limit und output_limit fix konfigurieren
  - EXTRACT: input_limit und output_limit fix konfigurieren
- Cache Hit‑Rate als KPI: Ziel mindestens 30 Prozent bei wiederkehrenden Threads
- External Provider ist default aus

### 8.2 Latenz
- LLM‑Calls sind der Haupttreiber. Optimierungen:
  - Deterministisches Kontext‑Packing: nur relevante Textabschnitte in den Prompt
  - Klassifikation vor Extraktion: wenn Klassifikation fail‑closed, Extraktion optional überspringen, um Kosten zu sparen

### 8.3 Privacy
- External LLM nur redacted und nur CLASSIFY (wenn überhaupt)
- Redaction Regeln deterministisch:
  - E‑Mail Adressen, Telefonnummern, IBAN werden gehasht oder maskiert
  - Polizzen und Claim Nummern können im LOCAL Prompt unredacted bleiben, extern nur gehasht

### 8.4 Rate‑Limits
- LLM Adapter implementiert:
  - globales Rate Limit (requests per minute)
  - queue‑based backpressure
  - bei 429: exponential backoff mit deterministischem Schedule und max Retries 2
  - danach fail‑closed zu Review

---

## 9) Migration, Phasenplan, Tests und Rollback

### 9.1 Migration in kleinen, kontrollierten Schritten
**Phase M1: Toggle + Audit + Cache**
- Implementiere config flags
- Implementiere LLM cache key und immutable LLM inference artifacts
- Audit Events für LLM calls
- Tests: determinism replay test, cache hit test

**Phase M2: LLM‑first Classification**
- LLM classification prompt strikt JSON
- Acceptance gates implementieren
- Disagreement gate implementieren
- Tests: regression auf sample corpus, new noisy corpus

**Phase M3: LLM‑first Extraction**
- LLM extraction prompt strikt JSON
- Entity validators implementieren
- Tests: entity pattern validation, identity impact test

**Phase M4: LLM‑assist in Identity**
- Identity assist prompt
- LLM signals nur mit Pattern plus Directory check
- Tests: typo recovery, no false confirm

### 9.2 Rollback (ein Schalter)
Rollback ist config‑only:
- `pipeline.mode = BASELINE`
- `llm.enabled = false`
- Alle Artefakte und Audit Events bleiben erhalten (append‑only)

### 9.3 Test Set Erweiterung
Empfohlen: Ergänze ein neues Sample Corpus für unstrukturierte E‑Mails:
- Tippfehler, Dialekt, gemischte Themen
- Gold Outputs mit canonical labels
- Metriken: Review Rate, Misroute, Misassociation

---

## 10) Konkretes Beispiel (deutsche Unfall‑E‑Mail mit Tippfehlern)

### 10.1 Beispiel Input (vereinfacht)
Subject: `Unfal mit meinem Auto bitte hilfe`  
Body (Auszug):
`Guten Tag, ich hatte gestern einen Unfal auf der A2 bei Wien. Meine Stossstange ist kaput. Polizze POL202400012345. Bitte sagen Sie mir wie ich den Schade melden soll. Fotos sind im Anhang.`

Attachment: Foto‑Text extrahiert (OCR leer oder minimal)

### 10.2 Baseline‑Modus Output (konservativ, fail‑closed)
**Classification (Baseline)**
- Intents: `INTENT_GENERAL_INQUIRY` und `INTENT_CLAIM_NEW`  
  Primary Intent: `INTENT_CLAIM_NEW` mit niedriger Confidence wegen Tippfehlern und unklarem Kontext  
- Product line: `PROD_AUTO` mit mittlerer Confidence  
- Urgency: `URG_NORMAL`  
- Risk flags: keine

**Routing (Baseline, wegen Unsicherheit in Classification und fehlender klarer Claims/Schaden‑Nr)**
- Queue: `QUEUE_CLASSIFICATION_REVIEW`
- Actions:
  - `ATTACH_ORIGINAL_EMAIL`
  - `ATTACH_ALL_FILES`
  - `ADD_REQUEST_INFO_DRAFT`
- Begründung: Unsicherheit über Intent‑Priorität und fehlende strukturierte Schadennummer, daher Review statt Auto‑Routing

### 10.3 LLM‑First Modus Output (robuster, aber gated)
**LLM‑First Classification**
- Intents:  
  - `INTENT_CLAIM_NEW` (primary)  
  - `INTENT_DOCUMENT_SUBMISSION` (weil Fotos im Anhang)  
- Product line: `PROD_AUTO`  
- Urgency: `URG_HIGH` (Unfallmeldung, Schaden, zeitnah)  
- Risk flags: keine

**LLM‑First Extraction**
- Entities:
  - `ENT_POLICY_NUMBER`: `POL-2024-00012345` (normalisiert aus `POL202400012345`), Confidence hoch, Pattern valid

**Identity**
- Mit polizzennr kann deterministic identity scoring Kandidat Policy matchen  
- Wenn Directory Lookup bestätigt: Identity Status wird mindestens probable, sonst needs review

**Routing (LLM‑First, wenn Gates alle bestanden)**
- Queue: `QUEUE_CLAIMS_AUTO`
- Actions:
  - `CREATE_CASE`
  - `ATTACH_ORIGINAL_EMAIL`
  - `ATTACH_ALL_FILES`
  - `ADD_REQUEST_INFO_DRAFT` (nur wenn Schaden‑Datum oder Ort nicht ausreichend extrahiert wurde; im Beispiel vorhanden, daher kann entfallen)

**Fail‑Closed Hinweis:**  
Wenn irgendein Gate scheitert (Schema invalid, Confidence zu niedrig, Evidence unplausibel), dann wird nicht auto‑routet, sondern `QUEUE_CLASSIFICATION_REVIEW` oder `QUEUE_IDENTITY_REVIEW` gewählt.

---

## Open Questions / Assumptions (minimiert, aber explizit)

1. **LLM Modellwahl lokal:** Es wird angenommen, dass ein lokales LLM verfügbar ist. Empfohlen ist ein Instruction‑Tuned Modell, das Deutsch gut abdeckt. Wenn nur Qwen2.5‑Coder‑7B‑Instruct verfügbar ist, wird es genutzt, aber Accuracy kann geringer sein.  
2. **Directory Lookup verfügbar:** Identity‑Confirm erfordert einen Directory Lookup oder interne Datenbank. Wenn nicht verfügbar, bleibt Identity häufiger `IDENTITY_NEEDS_REVIEW`.  
3. **OCR Qualität:** Wenn OCR nicht zuverlässig ist, bleibt Attachment‑Text als Signal schwach, LLM‑Input reduziert sich auf Body.

Diese Annahmen beeinflussen nur die erreichbare Review‑Reduktion, nicht die Fail‑Closed Sicherheit.
