# Habi Agency Copilot

Assistant conversationnel professionnel des PROPRIETAIRE et GERANT_AGENCE de
HabiTerra. Service Python indépendant du backend Spring Boot et de Habi Search AI.

> Le modèle de langage comprend la question et sélectionne un outil dans une liste
> fermée. Pydantic valide les paramètres. Spring Boot applique les permissions et
> récupère les informations réelles. FastAPI formule une réponse française et
> conserve les références nécessaires à la conversation.

## Installation et lancement Windows

Python 3.11 ou supérieur, un seul worker pour la mémoire locale. Depuis la racine :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8001
```

Ne pas remplacer un `.env` déjà configuré. Dans cmd.exe, activer avec
`.venv\Scripts\activate`. Sans activation PowerShell :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

Habi Search peut utiliser le port 8000 ; ce service utilise 8001.
Configurer la clé Groq uniquement dans `.env` ou l'environnement, jamais dans Git.
Démarrer Spring Boot séparément. Le JWT de l'utilisateur est fourni par le client,
pas enregistré dans `.env` par ce service.

## Configuration

`pydantic-settings` lit `.env` depuis le répertoire courant ; les variables
système ont priorité. Le fichier `.env` est ignoré par Git.

```dotenv
APP_NAME=Habi Agency Copilot
APP_ENV=development
SPRING_BOOT_BASE_URL=http://localhost:8080
SPRING_BOOT_TIMEOUT_SECONDS=5
GROQ_API_KEY=
COPILOT_LLM_MODEL=openai/gpt-oss-20b
COPILOT_LLM_TIMEOUT_SECONDS=20
COPILOT_MAX_TOOL_CALLS=5
COPILOT_CONVERSATION_TTL_MINUTES=30
```

Le modèle d'exemple figure dans la [liste des modèles Groq](https://console.groq.com/docs/models)
consultée pour cette étape. Son identifiant reste configurable ; aucun modèle
n'est imposé dans le client Python. Vérifier la disponibilité et l'autorisation
du modèle sur le compte Groq utilisé lors du déploiement.

Sans clé ou modèle, `/health` et OpenAPI restent accessibles. Un chat nécessitant
le planner renvoie `LLM_NOT_CONFIGURED` après authentification Spring.
Les dépendances sont FastAPI, Uvicorn, HTTPX, Pydantic, pydantic-settings,
python-dotenv et **groq** (SDK 0.37.1 installé lors de cette livraison).

## Architecture conservée

```text
POST /api/v1/copilot/chat + Authorization
  -> SpringAuthenticatedPrincipalResolver -> SpringBootClient -> GET /auth/me
  -> ConversationService -> ConversationStore (compte authentifié + UUID)
  -> PlannerService -> LLMClient -> Groq
  -> PlannerDecision validée
  -> résolution Python des références / types immobiliers
  -> ToolRegistry -> SpringBootClient -> Professional Read API
  -> ResponseService déterministe
  -> mémoire compacte et ChatResponse
```

Les dossiers existants conservent leurs responsabilités. Trois modules sont ajoutés :
`app/schemas/planner.py`, `app/core/text.py` et
`app/services/property_type_resolver.py`. Les huit handlers métier sont réutilisés.
SpringBootClient reste le seul composant qui appelle Spring Boot.

Aucun LangChain, LlamaIndex, SQL, ORM, accès DB, Redis, S3, OCR, Gemini, frontend,
streaming, WebSocket ou outil d'écriture. Habi Search n'est pas une dépendance.

## Groq et planner

`LLMClient` est un protocole indépendant du SDK. `GroqLLMClient` utilise AsyncGroq,
un timeout HTTP et une limite de durée totale par tentative. Les retries SDK
sont désactivés (`max_retries=0`). Les erreurs fournisseur sont converties en
messages fixes sans corps brut ni exception externe conservée comme contexte.

La requête utilise `response_format=json_schema`, en mode `strict=false` : le
schéma transmis guide la sortie, **Pydantic constitue la validation obligatoire**.
Ce choix accepte l'objet d'arguments variable des huit tools ; il ne prétend pas
garantir le schéma au niveau fournisseur. Voir les
[sorties structurées Groq](https://console.groq.com/docs/structured-outputs).

Une sortie JSON, décision ou argument invalide autorise **une seule réparation**.
La deuxième tentative reçoit la demande et une consigne fixe de correction ; la
sortie invalide et les détails d'erreur ne sont pas réinjectés. Deux appels Groq
au maximum, aucun retry sur timeout/indisponibilité, aucun `eval`.

Le prompt système complet se trouve dans `app/prompts/planner.py`. Il impose :
lecture seule, périmètre métier fermé, refus du scoring et des décisions locatives,
statuts Spring, références conceptuelles plutôt qu'identifiants inventés, champs
ciblés et traitement de toute donnée textuelle comme non fiable. Les schémas des
huit outils sont ajoutés au prompt depuis le registre, sans duplication manuelle.

### Structure exacte de PlannerDecision

```json
{
  "action": "CALL_TOOL",
  "tool": "get_property_details",
  "arguments": {},
  "reference": {
    "entity": "property",
    "kind": "POSITION",
    "position": 2,
    "explicitId": null
  },
  "propertyTypeLabel": null,
  "field": "rent",
  "expectSingle": false,
  "clarificationQuestion": null
}
```

- `action` : CALL_TOOL, NEEDS_CLARIFICATION, ANSWER_FROM_CONTEXT,
  READ_ONLY_REFUSAL ou UNSUPPORTED.
- `tool` : l'un des huit noms du registre, sinon null.
- `arguments` : objet JSON validé avec le modèle propre à l'outil ; défaut `{}`.
- `reference` : null ou entity (property/application/owner), kind
  (POSITION/LAST/SELECTED/EXPLICIT), position (1..10 ou null), explicitId (positif ou null).
- `propertyTypeLabel` : libellé à résoudre via le catalogue, ou null.
- `field` : champ d'intérêt dans une liste fermée (défaut summary).
- `expectSingle` : recherche d'une ressource singulière (défaut false).
- `clarificationQuestion` : question proposée ou null ; les formulations affichées
  sont choisies par Python pour ne pas exposer de texte métier inventé.

Seul CALL_TOOL accepte outil, arguments, référence, libellé de type ou expectSingle.
Les champs inconnus sont interdits. Le champ demandé doit être compatible avec
l'outil. La liste complète des valeurs de `field` est dans `schemas/planner.py`.

Une décision ne peut jamais fournir directement id/propertyId/typeId dans les
arguments. Python injecte l'identifiant résolu, puis revalide les arguments.
EXPLICIT exige un nombre réellement écrit après `id`, `identifiant` ou `#` dans
le message. Pour un candidat, on référence sa candidature, jamais une identité de session.

## Authentification et mémoire

Chaque chat exige `Authorization: Bearer <JWT HabiTerra>` et appelle
**GET /api/v1/auth/me** avant toute lecture de conversation ou appel Groq.
Le DTO existant est UserResponse ; seule sa propriété `id` est conservée.
Le scope interne est `habiterra:account:<id>`. Aucun userId fourni dans le body,
aucun décodage local de claims non validés, aucune décision locale d'autorisation.

Les appels métier transmettent à nouveau le JWT à Spring, qui vérifie à chaque
fois rôles, scopes, memberships ACTIF et accès. Le JWT n'est jamais enregistré
avec les arguments, en mémoire conversationnelle, dans les logs ou dans les réponses.

La conversation contient UUID, principal_id interne, created_at, expires_at et
un ConversationState :

```text
last_tool, last_field, last_arguments
last_properties, last_applications, last_owners
selected_property_id, selected_application_id, selected_owner_id
pending_clarification
last_facts
updated_at
```

Les listes conservent au maximum dix références affichées (id + libellé court).
Les faits mémorisés sont quelques compteurs, sans dossier, revenu déclaré complet,
réponse Spring brute ou transcription intégrale de la conversation.
Une clarification conserve la décision à reprendre et, si nécessaire, des options de type.

Le TTL est fixe depuis la création (30 minutes par défaut), avec purge aux accès.
La mémoire est locale, perdue au redémarrage, sans partage entre workers.
Un verrou temporaire par conversation sérialise les tours concurrents et est
retiré lorsqu'aucun tour ne l'utilise. Une conversation expirée pendant un tour
ne peut pas être réenregistrée.

Absent, expiré et appartenant à un autre compte produisent la même erreur
`CONVERSATION_UNAVAILABLE` (404), sans révéler l'existence ni le contenu.

ANSWER_FROM_CONTEXT ne restitue pas de données privées potentiellement périmées :
les faits métier sont relus via le dernier outil pour revalider les droits.
L'explication générale sur le revenu déclaré est déterministe et ne nécessite
aucun outil métier. L'authentification Spring reste obligatoire dans tous les cas.

## Références et clarifications

Python résout premier/deuxième/dernier vers la position dans la liste affichée,
puis vers l'id conservé. Le dernier signifie le dernier résultat **affiché**, pas
le dernier résultat de toutes les pages. Celui-ci/ce bien/son dossier utilisent
une sélection établie, ou une liste ne contenant qu'une seule ressource.
Une référence absente, hors liste ou ambiguë entraîne une clarification.

Une recherche singulière avec plusieurs résultats affiche une liste numérotée et
mémorise la question. Une réponse courte comme « Le deuxième » reprend cette
question sans nouvel appel LLM. Le détail est relu et autorisé par Spring.
Une nouvelle liste remplace les anciennes références de la même catégorie.

Pour une recherche de candidature ou propriétaire singulier, le détail/portefeuille
est demandé au tour suivant, afin de conserver un seul outil par message.

`PropertyTypeResolver` appelle le véritable **GET /api/v1/property-types** via
SpringBootClient. Contrat lu : `PropertyTypeResponse(Long id, String label,
String description)`, projeté sur id/label uniquement. Cache technique de cinq
minutes (catalogue public), normalisation casse/accents/espaces et pluriel simple.
Un libellé exact est privilégié ; plusieurs correspondances demandent un choix,
aucune correspondance demande une reformulation. Aucun id n'est codé en dur.
Ce catalogue et /auth/me ne sont pas des tools métier exposés au modèle.

## Réponses déterministes

ResponseService formule des listes, détails, KPI et dossiers en français, sans
second appel LLM. `field` cible la réponse : demander le loyer ne déclenche pas
un résumé complet. Les champs absents sont signalés, pas inventés.

- 750000 devient `750 000 FCFA` ; zéro reste zéro.
- DRAFT/AVAILABLE/RENTED/UNAVAILABLE deviennent brouillon/disponible/loué/indisponible.
- EN_ATTENTE/EN_ETUDE/ACCEPTEE/REJETEE/ANNULEE deviennent en attente/en étude/
  acceptée/rejetée/annulée.
- Les dates de candidature suivent la convention UTC du backend.
- Les KPI et la complétude viennent de Spring ; aucun recalcul local.
- Le revenu est toujours **déclaré**. Un justificatif présent ne garantit ni
  vérification du revenu, ni authenticité, ni véracité du contenu.

Les mutations usuelles sont refusées avant même le planner. Le prompt complète
ce garde-fou et le registre fermé ne possède aucune opération d'écriture.
Les demandes de scoring, classement au mérite ou recommandation de décision
locative sont refusées. Les questions hors périmètre reçoivent une explication
courte, sans réponse généraliste.

## Protection des données et des instructions

Les résultats Spring, labels métier, descriptions, revenus et documents ne sont
**jamais transmis au LLM**. Son contexte ne contient que dernier outil/champ,
nombres de références, présence d'une sélection et catégorie de clarification.
Il reçoit la question utilisateur filtrée, pas le principal, les JWT ou la clé API.

Les messages contenant des secrets configurés, formes courantes de jetons,
coordonnées ou liens sont refusés avant Groq. Ce filtrage conservateur n'est pas
un système général de détection de toutes les données sensibles possibles.
Les labels affichés sont raccourcis et nettoyés ; un titre contenant une instruction
reste une donnée affichée, jamais une consigne exécutée ou envoyée au planner.

Les logs applicatifs ne contiennent que conversationId, action, nom du tool,
durées, statut et catégorie d'erreur. Pas de message utilisateur, arguments,
payload Spring, token, clé ou traceback privé. Les logs des bibliothèques Groq,
HTTPX et HTTPCore sont neutralisés à l'initialisation du client LLM, y compris
si GROQ_LOG=debug est présent, pour éviter la journalisation des prompts/options.

## Endpoint chat et erreurs

`POST /api/v1/copilot/chat`, avec Authorization dans le header.

```json
{"conversationId":null,"message":"Accepte cette candidature."}
```

Exemple de structure après authentification réussie (UUID illustratif) :

```json
{
  "conversationId":"df67cfe1-982a-45f7-b661-179563b08f27",
  "status":"READ_ONLY",
  "answer":"Je peux consulter et résumer les informations, mais pas les modifier. Effectuez cette action dans HabiTerra.",
  "toolCalls":[],
  "suggestions":[],
  "errorCode":null
}
```

Les statuts sont ANSWERED, NEEDS_CLARIFICATION, READ_ONLY, UNSUPPORTED, ERROR.
`toolCalls` expose seulement les noms des appels métier tentés, jamais arguments
ou tokens. Les refus et clarifications normaux répondent HTTP 200. Une erreur
retourne status=ERROR et conserve le statut HTTP correspondant.

| Erreur | HTTP / code |
| --- | --- |
| Header absent/mal formé ou JWT refusé/expiré | 401 / UNAUTHORIZED |
| Accès Spring refusé | 403 / SPRING_FORBIDDEN |
| Ressource Spring introuvable | 404 / SPRING_NOT_FOUND |
| Conversation absente, expirée ou étrangère | 404 / CONVERSATION_UNAVAILABLE |
| Body chat invalide | 422 / INVALID_ARGUMENTS |
| Paramètres refusés par Spring (400/422) | 422 / SPRING_VALIDATION_ERROR |
| Décision toujours invalide après réparation | 502 / INVALID_PLANNER_DECISION |
| Réponse Spring incompatible | 502 / SPRING_INVALID_RESPONSE |
| Spring réseau/5xx | 503 / SPRING_UNAVAILABLE |
| Clé/modèle Groq absent ou configuration refusée | 503 / LLM_NOT_CONFIGURED |
| Groq réseau, surcharge ou 5xx | 503 / LLM_UNAVAILABLE |
| Timeout Spring / Groq | 504 / SPRING_TIMEOUT ou LLM_TIMEOUT |
| Erreur interne inattendue | 500 / INTERNAL_ERROR |

Aucun corps d'erreur externe, secret ou stacktrace n'est exposé.
Une panne Spring n'est jamais remplacée par une réponse métier inventée.

## Autres endpoints et limites d'appels

- GET /health : HTTP 200, `{"status":"ok","service":"habi-agency-copilot"}`.
- `/docs` : Swagger ; `/openapi.json` : OpenAPI.
- POST `/api/v1/copilot/tools/{tool_name}/execute` reste disponible uniquement pour
  APP_ENV=development. Il est absent des routes et d'OpenAPI en production.

COPILOT_MAX_TOOL_CALLS accepte 1..5, défaut 5. Le MVP applique un plafond effectif
**min(1, configuration)** par message : pas de boucle agent ni orchestration avancée.
/auth/me, le catalogue technique et la réparation Groq ne sont pas des tools métier.
Au plus deux tentatives Groq, 20 secondes chacune par défaut ; un appel métier.

## Contrat Spring de référence

Le backend voisin n'a pas été modifié. Les huit contrats proviennent de
`../HabiTerra BackEnd/PROFESSIONAL_READ_API.md`, ProfessionalReadController,
ProfessionalDtos, PropertyFilterRequest, enums et services associés.
/auth/me a été confirmé dans AuthController, AuthService et la sécurité JWT.
Le catalogue a été confirmé dans PropertyTypeController et PropertyTypeResponse.

La pagination modélisée conserve les champs PageImpl DIRECT : content, number,
size, totalElements, totalPages. Cette configuration a été confirmée dans les
sources locales Spring Boot/Data 4.1.1 ; sa forme HTTP réelle reste à valider.

## Vérifications de cette livraison

Aucune suite pytest ni nouveau dossier de tests. Vérifications ponctuelles :

- Imports et chargement FastAPI/OpenAPI.
- Démarrage Uvicorn sur 8001 ; health, docs et OpenAPI en HTTP 200.
- Chat sans Authorization en 401, body invalide en 422.
- Parsing Pydantic du planner, noms et arguments interdits refusés avant appel métier.
- Scénarios A à F vérifiés avec LLM et transport Spring **contrôlés localement**.
- Référence deuxième vers l'id réel de la fixture, ambiguïté, sélection sans LLM.
- Isolation entre comptes, expiration TTL, mémoire sans JWT ni dossier complet.
- Format FCFA, revenu déclaré et distinction présence/vérification.
- Contrat du SDK AsyncGroq et mapping réseau/timeout vérifiés avec transport local.

Ces contrôles ne prouvent pas la compréhension par le modèle réel. Aucun appel
Groq réel n'a été réalisé : la clé n'est pas disponible. Aucun succès métier réel
Spring n'a été obtenu : backend indisponible sur localhost:8080 et JWT de test absent.
Le refus de connexion réel à Spring produit bien HTTP 503, sans faux résultat.

Limites : un worker, mémoire volatile, dix références affichées par liste, ordinals
français usuels, correspondances de types conservatrices, un outil par message.
Le comportement linguistique et les permissions réelles doivent encore être
validés avec Groq et Spring configurés. L'orchestration multi-outils avancée reste
hors périmètre et nécessite une validation séparée.

## Arguments exacts des huit outils

Tous les modèles d'arguments sont stricts, `extra="forbid"`. Pas de conversion
silencieuse d'une chaîne en entier ou d'un entier en booléen. Les dates sont
au format ISO `YYYY-MM-DD`. Les noms JSON sont ceux de Spring.

Pagination commune `P` : `page` entier >= 0 (défaut 0), `size` entier 1..100
(défaut 20), avec `page * size <= 2147483647`.
Pour les recherches et le portefeuille propriétaire, `sort` est une liste de
chaînes, par exemple `["montantLoyer,asc","id,asc"]` (défaut `[]`). Chaque entrée
est transmise comme un paramètre query `sort` distinct. Une entrée accepte un
champ seul ou `champ,asc` / `champ,desc`. Spring applique les tris par défaut et
ajoute le tri stabilisateur par id.

Filtres immobiliers `F`, tous facultatifs et pouvant être null :

- `country`, `city`, `municipality`, `neighborhood` : chaînes, maximum 255 caractères.
- `typeId` : entier positif Long Java.
- `minRent`, `maxRent`, `rooms`, `bedrooms`, `bathrooms`, `minArea`, `maxArea` :
  entiers Integer Java >= 0 ; minimum <= maximum quand tous deux renseignés.
- `furnished`, `sharedHousingAllowed` : booléens.
- `minSharedHousingCapacity` : entier positif Integer Java ; exige `sharedHousingAllowed=true`.
- `availableBefore` : date ISO.

Statuts immobiliers confirmés : `DRAFT`, `AVAILABLE`, `RENTED`, `UNAVAILABLE`.
Statuts candidatures confirmés : `EN_ATTENTE`, `EN_ETUDE`, `ACCEPTEE`, `REJETEE`, `ANNULEE`.
Périodes confirmées : `TODAY`, `THIS_WEEK`, `THIS_MONTH`.

| Outil / modèle d'arguments | Champs autorisés | Transport Spring |
| --- | --- | --- |
| search_my_properties / SearchMyPropertiesArguments | `filters` objet F facultatif, `status` immobilier facultatif, P, `sort` | POST `/api/v1/professional/properties/search` ; corps filters/status, pagination/tri en query |
| get_property_details / GetPropertyDetailsArguments | `id` entier positif obligatoire | GET `/api/v1/professional/properties/{id}` |
| search_my_owners / SearchMyOwnersArguments | `search` chaîne <=255 facultative, P, `sort` | POST `/api/v1/professional/owners/search` ; corps search, pagination/tri en query |
| get_owner_portfolio / GetOwnerPortfolioArguments | `id` positif obligatoire, tous les champs F à plat, `status` facultatif, P, `sort` | GET `/api/v1/professional/owners/{id}/portfolio` ; tous les filtres à plat en query |
| search_my_applications / SearchMyApplicationsArguments | `status`, `propertyId` positif, `fromDate`, `toDate`, `period` facultatifs, P, `sort` | POST `/api/v1/professional/applications/search` ; corps des filtres, pagination/tri en query |
| get_application_details / GetApplicationDetailsArguments | `id` entier positif obligatoire | GET `/api/v1/professional/applications/{id}` |
| get_portfolio_kpis / GetPortfolioKpisArguments | aucun, `{}` | GET `/api/v1/professional/kpis/portfolio` |
| get_application_kpis / GetApplicationKpisArguments | P et `topLimit` entier 1..20, défaut 5 | GET `/api/v1/professional/kpis/applications` ; query page/size/topLimit |

Tris autorisés :

- Biens et portefeuille : `id`, `dateCreation`, `titre`, `montantLoyer`, `superficie`, `statut`.
- Propriétaires : `id`, `nom`, `prenom`.
- Candidatures : `id`, `dateCandidature`, `statut`.

Pour les candidatures, `period` exclut `fromDate`/`toDate` ; si les deux dates sont
présentes, `fromDate < toDate`, fin exclusive. Aucun paramètre `period` ou `sort`
n'est accepté par les KPI candidatures. Les id sélectionnent des ressources,
jamais le scope de session. Aucun userId/agencyId/tenantId n'est accepté.

## Résultats exacts des huit outils

L'endpoint de développement retourne directement le modèle Pydantic sérialisé.
Le chat transforme ces mêmes résultats en réponse française dans ChatResponse.
`Page<T>` contient `content: T[]`, `number`, `size`, `totalElements`, `totalPages`.
Les autres métadonnées techniques de PageImpl sont ignorées.
Les champs externes non modélisés sont écartés, jamais retransmis tels quels.

| Outil | Résultat |
| --- | --- |
| search_my_properties | Page<PropertyDetails> |
| get_property_details | PropertyDetails |
| search_my_owners | Page<OwnerSummary> |
| get_owner_portfolio | Page<PropertyDetails> |
| search_my_applications | Page<ApplicationSummary> |
| get_application_details | ApplicationDetails |
| get_portfolio_kpis | PortfolioKpis |
| get_application_kpis | ApplicationKpis |

Champs des modèles (voir les types et nullabilités dans `app/schemas/spring.py`) :

- **PropertyDetails** : id, title, status, rent, deposit, typeId, type, city,
  municipality, neighborhood, area, rooms, bedrooms, bathrooms, furnished,
  sharedHousingAllowed, availableFrom. Les données immobilières facultatives restent null.
- **OwnerSummary** : ownerId, displayName. Aucune coordonnée ni numéro d'identité.
- **PropertySummary** : id, title, monthlyRent.
- **ApplicationInfo** : id, status, applicationDate (convention UTC du LocalDateTime Spring).
- **ApplicationSummary** : champs ApplicationInfo + property: PropertySummary, candidateLabel.
- **ApplicationDetails** : application: ApplicationInfo, property: PropertySummary,
  candidate: Candidate, documents: Documents, completeness: DossierCompleteness.
- **Candidate** : profession, professionalSituation, monthlyIncomeDeclared ; chacun nullable.
- **Documents** : identityDocumentProvided, incomeProofProvided (booléens).
- **DossierCompleteness** : complete, completionPercentage, missingItems (liste de chaînes).
- **Distribution** : value (chaîne nullable), count.
- **PortfolioKpis** : totalProperties, availableProperties, draftProperties,
  rentedProperties, unavailableProperties, averageRent (nullable), distributionByType,
  distributionByCity, distributionByNeighborhood (listes de Distribution).
- **PropertyApplicationCount** : propertyId, title (nullable), applicationCount.
- **ApplicationKpis** : totalApplications, pendingApplications, underReviewApplications,
  acceptedApplications, rejectedApplications, cancelledApplications, receivedThisWeek,
  receivedThisMonth, applicationsByProperty: Page<PropertyApplicationCount>,
  topPropertiesByApplications: PropertyApplicationCount[],
  propertiesWithoutApplications: Page<PropertyApplicationCount>.

Le revenu est **déclaré**. Un justificatif présent ne prouve ni son authenticité
ni la vérification du revenu. Aucun scoring ni décision recommandée n'est produit.
Les compteurs et la complétude proviennent exclusivement de Spring.
