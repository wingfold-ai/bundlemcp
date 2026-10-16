## MODIFIED Requirements

### Requirement: AUTH-23 Name, scope and kind
Keys SHALL carry a `name`, unique among all keys, an optional **endpoint scope** (list of endpoint ids; empty = all
endpoints), and a **kind**: `endpoint` (can call scoped endpoints) or `service` (can also call the management API).
Creating a key under a name another key already has SHALL be refused with 409.

#### Scenario: Scoped key outside its scope
- **WHEN** a key scoped to endpoint `a` is presented at endpoint `b`
- **THEN** the request is not authenticated by that key

#### Scenario: Endpoint key at the management API
- **WHEN** an `endpoint`-kind key calls the management API
- **THEN** the gateway answers 403, while a `service`-kind key is accepted

#### Scenario: Duplicate key name
- **GIVEN** a key named `ci` exists
- **WHEN** an admin creates another key named `ci`
- **THEN** the gateway answers 409 and no key is created
