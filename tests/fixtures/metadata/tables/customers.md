# customers

format: 1
purpose: One row per customer account.

## Columns

- name [searchable]: Display name as entered at signup.
- email [sensitive]: Contact address.
- password_hash [hidden]: Never shown.
- region: Sales region code.
  - values: north, south
