# Spec Delta

## ADDED Requirements

### Requirement: DOC-18 A page for metamcp users
The documentation site MUST publish a guide page, `/guide/coming-from-metamcp`, listed in the Guide section of the
sidebar, for someone who runs metamcp and is deciding whether to move. The page has these parts:

- **How the concepts map:** a table with one row for each metamcp concept: MCP servers, namespaces, tool overrides,
  endpoints, API keys and middleware. Each row names the bundlemcp concept it becomes and says what differs.
- **What bundlemcp leaves out:** every entry of the decision log
  ([openspec/README.md](../../README.md#decision-log--deliberately-dropped-from-metamcp)) that a metamcp user would
  notice. Each one says what to do instead, or that there is no replacement.
- **Moving a setup over:** a manual migration through a bootstrap document, applied at startup or through import, with
  a worked example that takes a small metamcp setup to its bootstrap document. It names the metamcp importer as a
  roadmap theme, not as something that exists.
- **What you gain:** what bundlemcp adds over metamcp, each item linking the docs page that describes it.

The page names the metamcp release it compares against, and links metamcp's own documentation where it describes
metamcp. Like every page, it describes only bundlemcp behaviour that has shipped ([DOC-2](spec.md)). The repository
README's comparison with metamcp, and the roadmap's "What bundlemcp won't do" section ([DOC-16](spec.md)), link it.

#### Scenario: A metamcp user finds the page
- **WHEN** a visitor searches the site for "metamcp"
- **THEN** the page is among the results, and the Guide section of the sidebar lists it

#### Scenario: Every metamcp concept has a counterpart or a reason
- **WHEN** a reader looks up a metamcp concept from the mapping table
- **THEN** the table names the bundlemcp concept it becomes, or the page says why bundlemcp leaves it out and what
  to do instead

#### Scenario: The importer is not described as shipped
- **WHEN** a reader looks for a one-step migration
- **THEN** the page describes the manual migration through a bootstrap document, and names the importer only as a
  roadmap theme, linking the roadmap

#### Scenario: The worked example applies
- **WHEN** the bootstrap document from the page's worked example is applied to a gateway
- **THEN** it creates the upstreams, bundles and endpoints the example describes, with no validation error

#### Scenario: Claims about metamcp are traceable
- **WHEN** a reader checks what the page says about metamcp
- **THEN** the page names the metamcp release it compared against and links metamcp's documentation
