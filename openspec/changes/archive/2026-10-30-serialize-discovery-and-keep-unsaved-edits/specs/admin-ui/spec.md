## ADDED Requirements

### Requirement: UI-14 Unsaved edits survive a refresh
A form field or table row the admin has changed and not yet saved SHALL keep the admin's value when the data behind it
is read from the gateway again, whatever caused the read: another card's action, a save elsewhere on the page or a
background refetch. A field the admin has not changed SHALL take the gateway's new value. Once a save succeeds and the
gateway reports the saved value, the field counts as unchanged again.

#### Scenario: A refetch does not undo typing
- **GIVEN** the admin has typed a new description into a bundle's meta card and not saved it
- **WHEN** another card's action on the same page makes the bundle be read again
- **THEN** the description field still shows what the admin typed, and saving sends that value

#### Scenario: Untouched fields follow the gateway
- **GIVEN** the admin has changed a bundle's description but not its catalogue overview
- **WHEN** the bundle is read again and its overview was changed elsewhere meanwhile
- **THEN** the overview field shows the new overview and the description field keeps the admin's edit

#### Scenario: A saved field follows the gateway again
- **GIVEN** the admin saved a new description and the gateway reports it
- **WHEN** the description is later changed elsewhere and the bundle is read again
- **THEN** the description field shows the newer value
