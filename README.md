# Habi Agency Copilot

Service Python + FastAPI indépendant de **HabiTerra BackEnd Spring Boot** et de
**Habi Search AI**. Assistant destiné aux PROPRIETAIRE et GERANT_AGENCE.
Cette étape implémente seulement la lecture déterministe :

```text
FastAPI (endpoint de développement)
  -> ToolRegistry (nom fermé + arguments Pydantic stricts)
  -> handler = méthode explicite de SpringBootClient
  -> Spring Boot Professional Read API
  -> réponse Pydantic projetée, sans génération de texte
```

Spring Boot décide de l'identité, des rôles, permissions, scopes propriétaire/agence,
memberships ACTIF et accès aux ressources. Il fournit aussi les KPI. FastAPI ne
recalcule pas les KPI et ne décide jamais si un compte peut voir un bien.
Habi Search n'est pas une dépendance. Aucun LLM, SDK Groq, planner IA, accès S3,
SQL, ORM, base de données, Redis ou action d'écriture.

## Installation et lancement Windows

Python 3.11 ou supérieur. Depuis la racine du projet dans PowerShell :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8001
```

Dans cmd.exe, activer avec `.venv\Scripts\activate`.
Sans activation PowerShell :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

Le port local est **8001** ; Habi Search peut utiliser 8000. Les dépendances restent
fastapi, uvicorn, httpx, pydantic, pydantic-settings et python-dotenv.

## Configuration

`pydantic-settings` lit `.env` depuis le répertoire courant ; les variables
d'environnement sont prioritaires. Aucun secret réel n'est versionné.

| Variable | Valeur par défaut |
| --- | --- |
| APP_NAME | Habi Agency Copilot |
| APP_ENV | development |
| SPRING_BOOT_BASE_URL | http://localhost:8080 |
| SPRING_BOOT_TIMEOUT_SECONDS | 5 |
| GROQ_API_KEY | vide, inutilisée |
| COPILOT_LLM_MODEL | vide, inutilisé |
| COPILOT_CONVERSATION_TTL_MINUTES | 30 |

Le timeout et le TTL doivent être positifs. `.env` est ignoré par Git.
**Définir APP_ENV=production pour un déploiement** : la route d'exécution des tools
n'est enregistrée que pour la valeur exacte `development`. Redémarrer le service
après modification de l'environnement.

## Architecture existante

```text
app/
  main.py                         # cycle de vie, routes, erreurs expurgées
  core/config.py                  # configuration
  core/exceptions.py              # erreurs locales et Spring
  api/v1/copilot.py               # chat 501 + exécution de développement
  schemas/chat.py
  schemas/conversation.py
  schemas/tools.py                # huit arguments + définitions d'outils
  schemas/spring.py               # requêtes, enums, réponses, pagination
  clients/spring_client.py        # seul accès HTTP Spring
  clients/llm_client.py           # abstraction inactive
  services/copilot_service.py     # chat non implémenté
  services/conversation_service.py # résolution d'identité via Spring
  services/planner.py             # emplacement inactif
  services/response_service.py    # emplacement inactif
  tools/registry.py
  tools/properties.py
  tools/owners.py
  tools/applications.py
  tools/kpis.py
  memory/models.py
  memory/store.py                 # mémoire locale non reliée au chat
  prompts/planner.py              # emplacement inactif
  prompts/responder.py            # emplacement inactif
tests/.gitkeep                    # aucune suite de tests
.env.example
.gitignore
requirements.txt
README.md
```

Aucun fichier applicatif supplémentaire n'a été nécessaire pour cette étape.

## Sources du contrat effectivement lues

Projet voisin : `../HabiTerra BackEnd/` (consulté, non modifié).

- `PROFESSIONAL_READ_API.md`.
- `src/main/java/com/habiterra/professional/controller/ProfessionalReadController.java`.
- `professional/dto/ProfessionalDtos.java`, `professional/service/ProfessionalReadService.java`,
  `ProfessionalPeriods.java` et `ProfessionalKpiService.java` sous la même racine Java.
- `property/dto/PropertyFilterRequest.java`, `property/entity/StatutBien.java`.
- `application/entity/StatutCandidature.java`.
- `tenantprofile/dto/DossierCompletenessResponse.java`.
- `identity/controller/AuthController.java`, `identity/dto/UserResponse.java`,
  `identity/service/AuthService.java`, `shared/security/SecurityConfig.java`
  et `JwtAuthenticationFilter.java`.

Les sources locales Spring Boot/Data 4.1.1 ont également confirmé les valeurs par
défaut : page de 20 éléments, sérialisation `PageSerializationMode.DIRECT`.
Aucun remplacement VIA_DTO n'a été trouvé dans la configuration du backend.
Le texte `page.totalElements` dans le document métier n'est donc pas traité comme
une preuve d'une enveloppe JSON `page` : la projection conserve les propriétés
PageImpl `content`, `number`, `size`, `totalElements`, `totalPages`.
La sérialisation réelle devra encore être confirmée sur le backend en marche.
La stabilité de DIRECT n'est pas garantie par Spring Data : voir la
[documentation officielle](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/config/EnableSpringDataWebSupport.PageSerializationMode.html).

## Endpoints FastAPI

- `GET /health` : HTTP 200, `{"status":"ok","service":"habi-agency-copilot"}`.
  Ce contrôle ne contacte ni Spring Boot ni un fournisseur LLM.
- `POST /api/v1/copilot/chat` : HTTP 501 `NOT_IMPLEMENTED` pour un corps valide
  tel que `{"message":"Bonjour","conversationId":null}`. Aucun accès métier.
- `POST /api/v1/copilot/tools/{tool_name}/execute` : uniquement en développement.
- `/docs` : Swagger UI ; `/openapi.json` : OpenAPI 3.1.0.

Le endpoint de développement reçoit exactement :

```json
{"arguments":{"id":45}}
```

Le JWT vient uniquement du header `Authorization: Bearer <JWT HabiTerra>`.
Un header absent, vide, ambigu ou mal formé produit HTTP 401. La vérification
locale porte seulement sur la syntaxe Bearer, jamais sur l'identité ou les droits.
Spring valide le JWT. L'endpoint de chat reste désactivé et n'exige pas encore
l'authentification. Les champs inconnus dans le body sont refusés sans écho de leur valeur.

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

Le résultat HTTP est directement le modèle Pydantic sérialisé, sans enveloppe IA.
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

## Exécution et erreurs

`ToolRegistry.execute_tool(tool_name, arguments, authorization)` :

1. Recherche dans les huit définitions immuables ; nom inconnu refusé avant réseau.
2. Validation JSON Pydantic stricte avec le modèle de l'outil.
3. Contrôle de présence/syntaxe Authorization.
4. Appel du handler lié à une méthode nommée de SpringBootClient.
5. Retour d'un résultat Pydantic après parsing de la réponse Spring.

Chaque définition associe nom, description, modèle d'arguments, modèle de résultat
et handler. Aucune inscription dynamique, aucun outil HTTP générique, aucune URL
issue des arguments. Le transport HTTP privé sert uniquement les méthodes fixes.
Le client HTTP partagé est créé au démarrage et fermé à l'arrêt. Pas de redirection,
de retry automatique ni de mise en cache des données métier.

| Origine | Exception / code | HTTP FastAPI |
| --- | --- | --- |
| 400 ou 422 Spring | SpringValidationError / SPRING_VALIDATION_ERROR | 422 |
| 401 Spring ou header absent/mal formé | SpringUnauthorizedError / UNAUTHORIZED | 401 |
| 403 Spring | SpringForbiddenError / SPRING_FORBIDDEN | 403 |
| 404 Spring | SpringNotFoundError / SPRING_NOT_FOUND | 404 |
| 5xx Spring ou erreur réseau | SpringUnavailableError / SPRING_UNAVAILABLE | 503 |
| Timeout HTTPX | SpringTimeoutError / SPRING_TIMEOUT | 504 |
| JSON/réponse incompatible | SpringResponseError / SPRING_INVALID_RESPONSE | 502 |
| Autre statut, dont redirection | SpringBootError / SPRING_ERROR | 502 |
| Outil inconnu | UnknownToolError / UNKNOWN_TOOL | 404 |
| Arguments/body invalides | InvalidToolArgumentsError / INVALID_ARGUMENTS | 422 |

Les messages sont fixes. Aucun body Spring brut, valeur d'argument, header ou
exception HTTPX n'est retourné ou journalisé. Les erreurs de validation HTTP
n'exposent pas le champ `input` de Pydantic. Les exceptions HTTPX ne sont pas
conservées comme causes/contextes des erreurs applicatives.

## JWT et identité pour la mémoire

Authorization est passé séparément des arguments sur **chaque appel**. Il n'est
ni stocké dans les headers partagés, ni loggé, ni retourné, ni écrit dans
ConversationState. Aucun décodage local des claims JWT.

Endpoint existant confirmé : **GET /api/v1/auth/me**.
DTO Java : `UserResponse(Long id, String prenom, String nom, String email,
String telephone, Role role, String photoProfil, String profession, String poste)`.
Le filtre JWT Spring valide le jeton, charge le compte actif et établit l'identité.
`AuthService.me` retourne ce compte actif. L'identifiant utilisable est **id** du
compte Utilisateur (Long), pas celui du propriétaire ou de l'agence.

`SpringBootClient.get_current_account` lit cet endpoint et projette seulement
`CurrentAccount.id`. Les autres informations ne sont pas conservées dans le modèle.
Ce n'est pas un neuvième outil : cette méthode n'est pas dans ToolRegistry.
`AuthenticatedPrincipalResolver` définit le contrat ;
`SpringAuthenticatedPrincipalResolver` produit `habiterra:account:<id>` après
succès de /auth/me. Aucun identifiant ne vient du body ou d'un JWT décodé localement.

La mémoire actuelle conserve UUID, état structuré et TTL fixe depuis création,
avec purge aux accès et copies des objets. Elle reste **non branchée au chat**.
Lors d'une prochaine étape, chaque accès mémoire devra résoudre l'identité via
Spring avant d'utiliser ce scope interne. Celui-ci isole les conversations mais
n'accorde aucun droit métier ; chaque lecture métier repasse par Spring.
La mémoire est par processus, perdue au redémarrage, limitée à un worker pour le MVP.
La résolution /auth/me devra être vérifiée avec un vrai JWT avant mise en production.

## Exécution manuelle en développement

Démarrer Spring Boot séparément. Dans Swagger `/docs`, utiliser **Authorize**
pour saisir un JWT de test HabiTerra, puis appeler l'endpoint de développement.
Ne pas mettre le JWT dans le JSON, les fichiers, les captures ou les rapports.
Exemples de corps (changer le nom d'outil dans l'URL) :

```json
{"arguments":{"filters":{"city":"Dakar","maxRent":400000},"status":"AVAILABLE","page":0,"size":20,"sort":["montantLoyer,asc"]}}
```

```json
{"arguments":{"id":45}}
```

```json
{"arguments":{"id":3,"city":"Dakar","status":"RENTED","page":0,"size":20}}
```

```json
{"arguments":{"status":"EN_ATTENTE","propertyId":45,"period":"THIS_WEEK"}}
```

```json
{"arguments":{"page":0,"size":20,"topLimit":5}}
```

Le dernier exemple correspond aux KPI candidatures ; pour les KPI portefeuille,
utiliser `{"arguments":{}}`.

## Validation effectuée pour cette étape

Aucune suite de tests créée ou lancée ; `tests/` reste réservé.
Vérifications ponctuelles réalisées avec l'environnement virtuel :

- Installation des six dépendances directes réussie.
- Import de tous les modules applicatifs réussi.
- Démarrage Uvicorn sur 127.0.0.1:8001 réussi.
- GET /health : HTTP 200, `{"status":"ok","service":"habi-agency-copilot"}`.
- GET /docs et /openapi.json : HTTP 200 ; OpenAPI 3.1.0.
- Chat : HTTP 501 NOT_IMPLEMENTED.
- Exécution sans Authorization : HTTP 401.
- Nom inconnu : HTTP 404 UNKNOWN_TOOL, avant appel métier.
- Arguments invalides sur chacun des huit outils : HTTP 422.
- Champs body supplémentaires refusés sans écho de leur valeur.
- Huit exemples d'arguments valides et schémas de résultats validés localement.
- APP_ENV=production : route debug absente d'OpenAPI et HTTP 404 en ASGI local.
- Mapping d'erreurs vérifié localement via MockTransport (statuts, JSON invalide,
  timeout, réseau), sans serveur Spring ni succès métier simulé.

**Intégration réelle non validée** : aucun service n'écoutait sur 127.0.0.1:8080
et aucun JWT de test n'était disponible dans les variables vérifiées.
Aucun des huit outils ni /auth/me n'a donc été validé avec le vrai backend.
Les réponses et les scopes réels devront être vérifiés quand Spring et un JWT
approprié seront disponibles ; notamment les pages et les cas 401/403/404.

Versions directes installées lors de cette livraison : FastAPI 0.142.4,
Uvicorn 0.54.0, HTTPX 0.28.1, Pydantic 2.13.5, pydantic-settings 2.15.0,
python-dotenv 1.2.4. `requirements.txt` conserve ses plages de versions.

La prochaine étape est la validation contre Spring Boot avec un compte de test,
puis le raccordement contrôlé de la mémoire. L'intégration LLM reste hors périmètre.
