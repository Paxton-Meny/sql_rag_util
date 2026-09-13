"""Determine the dialect and paramstyle from a PEP 249 connection."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from sql_rag_util.exceptions import DialectDetectionError
from sql_rag_util.sql.render import PARAMSTYLES

__all__ = ["Detected", "DRIVER_DIALECTS", "AMBIGUOUS_DRIVERS", "detect"]

DRIVER_DIALECTS: dict[str, str] = {
    "sqlite3": "sqlite",
    "psycopg": "postgres",
    "psycopg2": "postgres",
    "pg8000": "postgres",
    "pymysql": "mysql",
    "MySQLdb": "mysql",
    "mysql": "mysql",
    "mariadb": "mysql",
    "pymssql": "mssql",
}
AMBIGUOUS_DRIVERS: frozenset[str] = frozenset({"pyodbc", "jaydebeapi", "adbc_driver_manager"})


@dataclass(frozen=True, slots=True)
class Detected:
    """What detection found.

    Parameters
    ----------
    dialect
        Dialect name.
    paramstyle
        The driver's paramstyle, or ``None`` when the module does not report one.
    driver
        Top-level module name of the connection class.
    """

    dialect: str
    paramstyle: str | None
    driver: str


def _driver_of(connection: object) -> str:
    module = type(connection).__module__ or ""
    return module.split(".", 1)[0]


def _paramstyle_of(driver: str) -> str | None:
    module = sys.modules.get(driver)
    style = getattr(module, "paramstyle", None)
    return style if isinstance(style, str) and style in PARAMSTYLES else None


def detect(connection: object, *, dialect: str | None = None) -> Detected:
    """Return the dialect and paramstyle for ``connection``.

    Parameters
    ----------
    connection
        A PEP 249 connection object.
    dialect
        Explicit dialect name; wins over detection and is required for
        drivers that connect to more than one database.

    Raises
    ------
    DialectDetectionError
        When the driver is unknown or ambiguous and no dialect was given.
    """
    driver = _driver_of(connection)
    if dialect is None:
        if driver in AMBIGUOUS_DRIVERS:
            raise DialectDetectionError(
                f"{driver} connects to several databases; pass dialect= explicitly",
                suggestions=("sqlite", "mysql", "mssql", "postgres"),
            )
        dialect = DRIVER_DIALECTS.get(driver)
        if dialect is None:
            raise DialectDetectionError(
                f"cannot detect a dialect from driver {driver!r}; pass dialect= explicitly",
                suggestions=("sqlite", "mysql", "mssql", "postgres"),
            )
    return Detected(dialect, _paramstyle_of(driver), driver)
