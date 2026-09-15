"""Selectable authoritative targets shown by mapping and review interfaces."""

from mia_dpp.aas.templates import OfficialTemplateRepository, resolve_element
from mia_dpp.domain.mappings import NameplateElement
from mia_dpp.domain.targets import SubmodelTemplate, TemplateElement
from mia_dpp.tools.mapping.targets import ARBITRARY_PROPERTY_PATH, mapping_target

_KNOWN_ARBITRARY_TARGETS = (
    ("DegreeOfProtection", "0173-1#02-AAM634#003", "IP ingress-protection rating."),
    ("MeasuringRange", "0173-1#02-AAN401#003", "Operating or measuring range with unit."),
    (
        "ManufacturingSite",
        "0173-1#02-AAW336#001",
        "Plant or site where the product was manufactured.",
    ),
)


def selectable_elements(template: SubmodelTemplate) -> tuple[TemplateElement, ...]:
    """Return fixed value-bearing targets appropriate for a correction menu."""

    selected: list[TemplateElement] = []

    def visit(elements: tuple[TemplateElement, ...]) -> None:
        for element in elements:
            if (
                element.model_type in {"Property", "MultiLanguageProperty", "Range", "File"}
                and not element.wildcard
            ):
                selected.append(element)
            visit(element.children)

    visit(template.elements)
    return tuple(selected)


def nameplate_catalog(repository: OfficialTemplateRepository) -> tuple[NameplateElement, ...]:
    template = repository.load("digital_nameplate")
    result: list[NameplateElement] = []
    for element in selectable_elements(template):
        target = mapping_target(template, element.path)
        result.append(
            NameplateElement(
                name=target.id_short,
                path=target.instance_path,
                semantic_id=target.semantic_id.primary_value,
                hint=element.description or f"Official {element.model_type} target.",
                required=bool(element.cardinality and element.cardinality.minimum),
                model_type=element.model_type,
                value_type=element.value_type,
                target=target,
            )
        )
    arbitrary = resolve_element(template, ARBITRARY_PROPERTY_PATH)
    for name, semantic_id, hint in _KNOWN_ARBITRARY_TARGETS:
        target = mapping_target(
            template,
            ARBITRARY_PROPERTY_PATH,
            id_short=name,
            semantic_id=semantic_id,
        )
        result.append(
            NameplateElement(
                name=name,
                path=target.instance_path,
                semantic_id=semantic_id,
                hint=hint,
                required=False,
                model_type=arbitrary.model_type,
                value_type=arbitrary.value_type,
                target=target,
            )
        )
    return tuple(result)
