import tempfile
from typing import Any

from basiclive.utils.conf import AppSettings


def default_tag_function(entry: dict[str, Any]) -> list[str]:
    """
    Default tag function.
    Given a PDB report entry, generate a list of tags to apply to the entry when created in the database.
    """
    try:
        return [entry['diffrn_source.pdbx_synchrotron_beamline'].split()[-1]]
    except (KeyError, IndexError, AttributeError):
        return []


DEFAULTS: dict[str, Any] = {
    "PDB_FACILITY_ACRONYM": "CLSI",
    "CONTACT_EMAIL": "admin@example.com",
    "CROSSREF_API_KEY": None,
    "CROSSREF_THROTTLE": 1,
    "CROSSREF_BATCH_SIZE": 10,
    "CROSSREF_EVENTS_URL": "https://api.eventdata.crossref.org/v1/events/distinct",
    "CROSSREF_CITATIONS_URL": "https://www.crossref.org/openurl/",
    "GOOGLE_API_KEY": None,
    "OPEN_CITATIONS_KEY": None,
    "OPEN_CITATIONS_URL": "https://opencitations.net/index/api/v2/",
    "PDB_SEARCH_URL": "https://search.rcsb.org/rcsbsearch/v2/query",
    "PDB_REPORT_URL": "https://data.rcsb.org/graphql",
    "GOOGLE_BOOKS_API": "https://www.googleapis.com/books/v1/volumes",
    "SCIMAGO_URL": "https://www.scimagojr.com/journalrank.php",
    "PDB_TAG_FUNCTION": default_tag_function,
    "LOCAL_DIR": tempfile.gettempdir(),
    "PDB_URL_TEMPLATE": "https://www.rcsb.org/structure/{}",
    "PDB_IMAGE_URL_TEMPLATE": "https://cdn.rcsb.org/images/structures/{}_assembly-1.jpeg",
    "YEAR_FILTER_START": 2005,
}

settings = AppSettings("PUBLICATIONS", DEFAULTS)
