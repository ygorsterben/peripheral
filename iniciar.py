"""Ponto de entrada do Gerenciador de Periféricos (usado pelo PyInstaller e por "py iniciar.py").
Equivale a "py -m app". Use --bandeja para começar só com o ícone na bandeja."""
from app.__main__ import main

if __name__ == "__main__":
    main()
