# Architecture for contributors

## Package boundaries

The top-level dependency direction is `app → workflows → modules → shared`. The control feature follows `interfaces → application → persistence → contracts → domain`.

| Layer | Responsibility |
| --- | --- |
| `app` | Application factory, HTTP/CLI transports and lifecycle |
| `workflows` | Cross-feature orchestration for stateless anonymization and model content |
| `modules/control/interfaces` | Authenticated MCP tool and resource transport |
| `modules/control/application` | Invocation services, management use cases and composition facade |
| `modules/control/persistence` | Concrete memory accounting, identity/configuration, model, secret-detector and tool adapters |
| `modules/control/contracts` | Narrow ports used by the application services |
| `modules/control/domain` | Pydantic policy models, limits, privacy rules and signature checks |
| `shared` | Common Pydantic model and environment-backed settings |

The `persistence` package name identifies an implementation boundary; the runtime ledger stores nothing durably. Application services depend on ports. The facade composes concrete adapters, and the application factory composes the transports. Domain code has no HTTP, MCP or database dependency. Import-linter checks these boundaries.

All first-party records use Pydantic. Policy models are frozen; role/signature collections use tuples and rule mappings are immutable. Acquiring the active policy/feed snapshot returns an existing reference in O(1).
