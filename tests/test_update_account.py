from votacoes_assembleia_da_republica.update_account import update

def test_update_doesnt_crash_if_there_are_no_votes():
    update()
