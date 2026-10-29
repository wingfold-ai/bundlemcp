from pydantic import BaseModel, BeforeValidator, ValidationError


def valid_entries[M: BaseModel](model: type[M]) -> BeforeValidator:
    """A validator for a list in a third-party document that keeps only usable entries.

    A value that is not a list reads as empty. An entry that is not an object, or
    whose keys do not have the types the document's schema gives them, is
    skipped, so one malformed entry does not discard the rest of the document.
    """

    def keep(value: object) -> list[M]:
        if not isinstance(value, list):
            return []
        kept: list[M] = []
        for entry in value:
            if not isinstance(entry, dict):
                continue
            try:
                kept.append(model.model_validate(entry))
            except ValidationError:
                continue
        return kept

    return BeforeValidator(keep)
