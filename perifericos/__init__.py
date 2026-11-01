"""Protocolo do mouse Fire Phoenix BK-R6X e do teclado Aula F99 Pro (ver docs/).

Este pacote só fala com os aparelhos: não imprime nada e não encerra o programa. Erros viram exceções
(`ErroPeriferico` e derivadas), para o app e as ferramentas de `tools/` decidirem o que mostrar.
"""


class ErroPeriferico(Exception):
    """Base de todos os erros de comunicação com os aparelhos."""


class NaoEncontrado(ErroPeriferico):
    """O aparelho não está conectado por nenhum caminho conhecido."""


class SemResposta(ErroPeriferico):
    """O aparelho não respondeu (dormindo, desligado, fora de alcance ou parado)."""


class RespostaInvalida(ErroPeriferico):
    """Resposta inesperada, eco diferente ou leitura que não confere com o que foi gravado."""


class Dessincronizado(ErroPeriferico):
    """O dongle do mouse está entregando respostas deslocadas; só religando o dongle."""
