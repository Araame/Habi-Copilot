class CopilotError(Exception):
    status_code = 502
    code = "COPILOT_ERROR"
    message = "La demande ne peut pas être traitée actuellement."

    def __init__(self) -> None:
        super().__init__(self.message)


class LLMUnavailableError(CopilotError):
    status_code = 503
    code = "LLM_UNAVAILABLE"
    message = "Le service de compréhension est indisponible. Réessayez plus tard."


class LLMConfigurationError(LLMUnavailableError):
    code = "LLM_NOT_CONFIGURED"
    message = "Le service de compréhension n'est pas configuré."


class LLMTimeoutError(CopilotError):
    status_code = 504
    code = "LLM_TIMEOUT"
    message = "Le service de compréhension a dépassé le délai autorisé."


class InvalidPlannerDecisionError(CopilotError):
    code = "INVALID_PLANNER_DECISION"
    message = "Je n'ai pas pu interpréter cette demande de façon fiable. Pouvez-vous la reformuler ?"


class ConversationUnavailableError(CopilotError):
    status_code = 404
    code = "CONVERSATION_UNAVAILABLE"
    message = "Conversation inaccessible ou expirée. Veuillez démarrer une nouvelle conversation."


class ClarificationRequired(Exception):
    """Signal interne, sans erreur réseau ni données sensibles."""


class UnknownToolError(ValueError):
    """Le nom demandé ne figure pas dans le registre fermé."""


class InvalidToolArgumentsError(ValueError):
    """Arguments invalides, sans reprise des valeurs soumises."""


class SpringBootError(Exception):
    """Messages fixes : aucun body, URL, header ou exception HTTPX conservé."""

    status_code = 502
    code = "SPRING_ERROR"
    message = "Erreur de communication avec Spring Boot."

    def __init__(self) -> None:
        super().__init__(self.message)


class SpringValidationError(SpringBootError):
    status_code = 422
    code = "SPRING_VALIDATION_ERROR"
    message = "Paramètres refusés par Spring Boot."


class SpringUnauthorizedError(SpringBootError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "Authentification Bearer requise ou refusée par Spring Boot."


class SpringForbiddenError(SpringBootError):
    status_code = 403
    code = "SPRING_FORBIDDEN"
    message = "Accès refusé par Spring Boot."


class SpringNotFoundError(SpringBootError):
    status_code = 404
    code = "SPRING_NOT_FOUND"
    message = "Ressource absente ou inaccessible."


class SpringUnavailableError(SpringBootError):
    status_code = 503
    code = "SPRING_UNAVAILABLE"
    message = "Spring Boot est indisponible."


class SpringTimeoutError(SpringBootError):
    status_code = 504
    code = "SPRING_TIMEOUT"
    message = "Délai de réponse de Spring Boot dépassé."


class SpringResponseError(SpringBootError):
    code = "SPRING_INVALID_RESPONSE"
    message = "La réponse Spring Boot ne respecte pas le contrat attendu."
