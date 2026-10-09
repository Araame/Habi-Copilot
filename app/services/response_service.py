"""Formulation française déterministe. Aucun appel LLM, aucun KPI recalculé."""

from decimal import Decimal

from pydantic import BaseModel

from app.core.text import display_text
from app.schemas.spring import (
    ApplicationDetails, ApplicationKpis, PortfolioKpis, PropertyDetails, SpringPage,
)

PROPERTY_STATUS = {"DRAFT": "brouillon", "AVAILABLE": "disponible", "RENTED": "loué", "UNAVAILABLE": "indisponible"}
APPLICATION_STATUS = {"EN_ATTENTE": "en attente", "EN_ETUDE": "en étude", "ACCEPTEE": "acceptée", "REJETEE": "rejetée", "ANNULEE": "annulée"}
INCOME_NOTICE = (
    "Le revenu est déclaré par le candidat. La présence d'un justificatif ne constitue "
    "pas une vérification du revenu, de l'authenticité du document ou de son contenu."
)
READ_ONLY_ANSWER = "Je peux consulter et résumer les informations, mais pas les modifier. Effectuez cette action dans HabiTerra."
UNSUPPORTED_ANSWER = (
    "Je peux consulter les biens, propriétaires, candidatures et KPI professionnels de HabiTerra. "
    "Je ne réalise ni scoring, ni classement au mérite, ni recommandation de décision locative."
)


def format_fcfa(value: int | float | None) -> str:
    if value is None:
        return "non renseigné"
    amount = f"{Decimal(str(value)):,.2f}".rstrip("0").rstrip(".")
    return amount.replace(",", " ").replace(".", ",") + " FCFA"


def yes_no(value: bool | None) -> str:
    return "non renseigné" if value is None else "oui" if value else "non"


class ResponseService:
    def render(self, name: str, result: BaseModel, field: str = "summary") -> str | None:
        if isinstance(result, SpringPage):
            return self._page(name, result, field)
        if isinstance(result, PropertyDetails):
            return self._property(result, field)
        if isinstance(result, ApplicationDetails):
            return self._application(result, field)
        if isinstance(result, PortfolioKpis):
            return self._portfolio(result, field)
        if isinstance(result, ApplicationKpis):
            return self._applications_kpis(result, field)
        return None

    def _page(self, name: str, result: SpringPage, field: str) -> str | None:
        noun = "propriétaire(s)" if name == "search_my_owners" else "candidature(s)" if name == "search_my_applications" else "bien(s)"
        if field == "total":
            return f"La recherche correspond à {result.totalElements} {noun}."
        if field != "summary":
            return None
        if not result.content:
            return f"Aucun résultat sur cette page. La recherche correspond à {result.totalElements} {noun}."
        lines = []
        for index, item in enumerate(result.content[:10], 1):
            if name == "search_my_owners":
                text = display_text(item.displayName)
            elif name == "search_my_applications":
                text = (f"{display_text(item.candidateLabel)} — {APPLICATION_STATUS[item.status]}, "
                        f"{item.applicationDate.strftime('%d/%m/%Y %H:%M')} UTC, {display_text(item.property.title)}")
            else:
                text = f"{display_text(item.title)} — {PROPERTY_STATUS[item.status]}, loyer : {format_fcfa(item.rent)}"
            lines.append(f"{index}. {text}")
        return (f"{result.totalElements} {noun} correspondent à la recherche. "
                f"Page {result.number + 1} : {len(lines)} résultat(s) affiché(s).\n" + "\n".join(lines))

    def _property(self, item: PropertyDetails, field: str) -> str | None:
        values = {
            "rent": f"Le loyer mensuel est {format_fcfa(item.rent)}.",
            "deposit": f"La caution est {format_fcfa(item.deposit)}.",
            "status": f"Le bien est {PROPERTY_STATUS[item.status]}.",
            "area": f"La superficie est {str(item.area) + ' m²' if item.area is not None else 'non renseignée'}.",
            "rooms": f"Nombre de pièces : {item.rooms if item.rooms is not None else 'non renseigné'}.",
            "bedrooms": f"Nombre de chambres : {item.bedrooms if item.bedrooms is not None else 'non renseigné'}.",
            "bathrooms": f"Nombre de salles de bain : {item.bathrooms if item.bathrooms is not None else 'non renseigné'}.",
            "furnished": f"Meublé : {yes_no(item.furnished)}.",
            "sharedHousingAllowed": f"Colocation autorisée : {yes_no(item.sharedHousingAllowed)}.",
            "availableFrom": f"Disponible à partir du : {item.availableFrom.isoformat() if item.availableFrom else 'non renseigné'}.",
        }
        if field != "summary":
            return values.get(field)
        return (f"{display_text(item.title)} — {PROPERTY_STATUS[item.status]}.\n"
                f"Type : {display_text(item.type)} ; ville : {display_text(item.city)} ; quartier : {display_text(item.neighborhood)}.\n"
                + "\n".join(values[key] for key in ("rent", "deposit", "area", "bedrooms")))

    def _application(self, item: ApplicationDetails, field: str) -> str | None:
        candidate, documents, completeness = item.candidate, item.documents, item.completeness
        income = (f"Le candidat déclare un revenu mensuel de {format_fcfa(candidate.monthlyIncomeDeclared)}."
                  if candidate.monthlyIncomeDeclared is not None else "Le revenu mensuel déclaré n'est pas renseigné.")
        proof = "Un justificatif de revenu est présent dans son dossier." if documents.incomeProofProvided else "Aucun justificatif de revenu n'est présent dans son dossier."
        missing = ", ".join(display_text(value) for value in completeness.missingItems) or "aucun élément signalé"
        values = {
            "status": f"La candidature est {APPLICATION_STATUS[item.application.status]}.",
            "rent": f"Le loyer mensuel du bien est {format_fcfa(item.property.monthlyRent)}.",
            "monthlyIncomeDeclared": f"{income} {proof}",
            "profession": f"Profession déclarée : {display_text(candidate.profession)}.",
            "professionalSituation": f"Situation professionnelle déclarée : {display_text(candidate.professionalSituation)}.",
            "documents": f"Pièce d'identité présente : {yes_no(documents.identityDocumentProvided)}. {proof} {INCOME_NOTICE}",
            "completeness": f"Dossier complet : {yes_no(completeness.complete)}. Complétude : {completeness.completionPercentage} %. Éléments manquants : {missing}.",
            "incomeVerification": INCOME_NOTICE,
        }
        if field != "summary":
            return values.get(field)
        return "\n".join(values[key] for key in ("status", "profession", "professionalSituation", "monthlyIncomeDeclared", "documents", "completeness"))

    def _portfolio(self, item: PortfolioKpis, field: str) -> str | None:
        values = {
            "total": f"Vous gérez actuellement {item.totalProperties} bien(s).",
            "available": f"{item.availableProperties} bien(s) sont disponibles.",
            "rented": f"{item.rentedProperties} bien(s) sont loués.",
            "draft": f"{item.draftProperties} bien(s) sont en brouillon.",
            "unavailable": f"{item.unavailableProperties} bien(s) sont indisponibles.",
            "averageRent": f"Le loyer moyen du portefeuille, tous statuts confondus, est {format_fcfa(item.averageRent)}.",
        }
        if field in {"distributionByType", "distributionByCity", "distributionByNeighborhood"}:
            distribution = getattr(item, field)
            label = {"distributionByType": "type", "distributionByCity": "ville", "distributionByNeighborhood": "quartier"}[field]
            if not distribution:
                return f"Aucune répartition par {label} disponible."
            # Tri de présentation uniquement ; les compteurs proviennent de Spring.
            rows = sorted(distribution, key=lambda row: row.count, reverse=True)
            return f"Répartition par {label} (compteurs Spring Boot) :\n" + "\n".join(f"- {display_text(row.value)} : {row.count}" for row in rows)
        return "\n".join(values.values()) if field == "summary" else values.get(field)

    def _applications_kpis(self, item: ApplicationKpis, field: str) -> str | None:
        values = {
            "total": f"Vous avez reçu {item.totalApplications} candidature(s) au total.",
            "pending": f"{item.pendingApplications} candidature(s) sont en attente.",
            "underReview": f"{item.underReviewApplications} candidature(s) sont en étude.",
            "accepted": f"{item.acceptedApplications} candidature(s) sont acceptées.",
            "rejected": f"{item.rejectedApplications} candidature(s) sont rejetées.",
            "cancelled": f"{item.cancelledApplications} candidature(s) sont annulées.",
            "receivedThisWeek": f"{item.receivedThisWeek} candidature(s) reçues cette semaine.",
            "receivedThisMonth": f"{item.receivedThisMonth} candidature(s) reçues ce mois-ci.",
        }
        if field in {"applicationsByProperty", "propertiesWithoutApplications", "topPropertiesByApplications"}:
            data = getattr(item, field)
            rows = data if isinstance(data, list) else data.content
            heading = {"applicationsByProperty": "Candidatures par bien", "propertiesWithoutApplications": "Biens sans candidature", "topPropertiesByApplications": "Biens recevant le plus de candidatures"}[field]
            pagination = "" if isinstance(data, list) else f" — page {data.number + 1}, {data.totalElements} bien(s) au total"
            if not rows:
                return heading + pagination + " : aucun résultat sur cette page."
            return heading + pagination + " (10 résultats affichés au maximum) :\n" + "\n".join(
                f"{i}. {display_text(row.title)} : {row.applicationCount} candidature(s)" for i, row in enumerate(rows[:10], 1)
            )
        return "\n".join(values.values()) if field == "summary" else values.get(field)
