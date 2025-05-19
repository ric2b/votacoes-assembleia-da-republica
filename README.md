### Updates statuses
1. `poetry install`
2. `poetry run python3 -m votacoes_assembleia_da_republica.update_account`

### Debug mode
Set `DEBUG_MODE=true` in the environment to enable debug mode and print votes to the console instead of publishing, 
and to not update the stored state.

### Delete statuses
1. `poetry run python3 delete_statuses.py <since_minutes_ago>`

## Tests
`poetry run pytest`
