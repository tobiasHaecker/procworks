# SPDX-License-Identifier: BUSL-1.1
"""Data Access Layer and connector SPI (Section 9, step 12).

EXTERNAL data elements (see ``DataElement.source``) are not stored in the
process instance but resolved against a central database or business
application through a *connector*. The Data Access Layer (DAL) provides a
single, uniform read/write/query interface and routes each access to the
connector a data element is bound to.

Security by design:
  * Credentials/endpoints never live in the schema -- the connector instance
    holds them and is registered server-side.
  * The lookup key and write values are always passed as *parameters*
    (``read(entity, key)`` / ``write(entity, key, values)``); they are never
    concatenated into a query string, so there is no injection surface.

The in-memory connector below is the reference implementation used in tests
and demos; real connectors (MS SQL, MySQL, Dynamics 365, SAP) implement the
same ``Connector`` protocol.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from procworks.model import DataSourceKind, ExternalBinding, ProcessSchema

#: A single external record as returned/accepted by a connector.
Record = Mapping[str, object]


class DataAccessError(RuntimeError):
    """Raised when an external data access cannot be resolved or executed."""


class Connector(Protocol):
    """The narrow SPI every data connector implements.

    All accesses are parameterized: ``key`` and ``values`` are data, never
    interpolated into a statement.
    """

    def read(self, entity: str, key: object) -> Record:
        """Return the record of ``entity`` identified by ``key``."""
        ...

    def write(self, entity: str, key: object, values: Record) -> None:
        """Insert or update the record of ``entity`` identified by ``key``."""
        ...

    def query(self, entity: str, filters: Record) -> list[Record]:
        """Return all records of ``entity`` matching every key/value in ``filters``."""
        ...


class InMemoryConnector:
    """A simple dict-backed connector for tests and local demos."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[object, dict[str, object]]] = {}

    def read(self, entity: str, key: object) -> Record:
        try:
            return dict(self._rows[entity][key])
        except KeyError as exc:
            raise DataAccessError(
                f"no record '{key}' in entity '{entity}'"
            ) from exc

    def write(self, entity: str, key: object, values: Record) -> None:
        self._rows.setdefault(entity, {})[key] = dict(values)

    def query(self, entity: str, filters: Record) -> list[Record]:
        rows = self._rows.get(entity, {})
        return [
            dict(row)
            for row in rows.values()
            if all(row.get(field) == value for field, value in filters.items())
        ]


class DataAccessLayer:
    """Routes external data accesses of a schema to registered connectors."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector_id: str, connector: Connector) -> None:
        """Make a connector instance available under ``connector_id``."""

        self._connectors[connector_id] = connector

    def connector(self, connector_id: str) -> Connector:
        """Return the registered connector or raise ``DataAccessError``."""

        connector = self._connectors.get(connector_id)
        if connector is None:
            raise DataAccessError(f"connector '{connector_id}' is not registered")
        return connector

    def _binding(self, schema: ProcessSchema, element_id: str) -> ExternalBinding:
        element = schema.data_elements.get(element_id)
        if element is None:
            raise DataAccessError(f"unknown data element '{element_id}'")
        if element.source is not DataSourceKind.EXTERNAL or element.external is None:
            raise DataAccessError(f"data element '{element_id}' is not EXTERNAL")
        return element.external

    def _key(self, binding: ExternalBinding, instance_values: Record) -> object:
        if binding.key_element_id not in instance_values:
            raise DataAccessError(
                f"lookup key '{binding.key_element_id}' is not set in the instance"
            )
        return instance_values[binding.key_element_id]

    def read(
        self, schema: ProcessSchema, instance_values: Record, element_id: str
    ) -> Record:
        """Resolve and read an EXTERNAL element for the given instance values."""

        binding = self._binding(schema, element_id)
        key = self._key(binding, instance_values)
        return self.connector(binding.connector_id).read(binding.entity, key)

    def write(
        self,
        schema: ProcessSchema,
        instance_values: Record,
        element_id: str,
        values: Record,
    ) -> None:
        """Resolve and write an EXTERNAL element for the given instance values."""

        binding = self._binding(schema, element_id)
        key = self._key(binding, instance_values)
        self.connector(binding.connector_id).write(binding.entity, key, values)

    def query(
        self, schema: ProcessSchema, element_id: str, filters: Record
    ) -> list[Record]:
        """Query the entity an EXTERNAL element is bound to."""

        binding = self._binding(schema, element_id)
        return self.connector(binding.connector_id).query(binding.entity, filters)
