import json
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Confirm, Prompt

from core import VERSION, Jarvis, recall_memory, system_info

console = Console()


def confirm(message):

    console.print()
    console.print(
        f"[yellow]{message}[/yellow]"
    )

    return Confirm.ask(
        "Autorizar?",
        default=False
    )


agent = Jarvis(confirm)


def main():

    if len(sys.argv) > 1:

        prompt = " ".join(sys.argv[1:])

        answer, backend = agent.ask(prompt)

        console.print(Markdown(answer))
        console.print(
            f"\n[dim]{backend}[/dim]"
        )

        return

    console.print()
    console.print(
        f"[bold cyan]JARVIS V{VERSION.split('.')[0]}[/bold cyan]"
    )
    console.print(
        "[dim]LambdaWS Agent[/dim]"
    )
    console.print()

    while True:

        try:

            prompt = Prompt.ask(
                "[bold cyan]Você[/bold cyan]"
            )

        except (EOFError, KeyboardInterrupt):

            break

        if prompt in (
            "/exit",
            "/quit"
        ):
            break

        if prompt == "/clear":

            agent.clear()

            console.print(
                "[green]Memória limpa.[/green]"
            )

            continue

        if prompt == "/status":
            console.print_json(json.dumps(system_info(), ensure_ascii=False))
            continue

        if prompt == "/memory":
            console.print_json(json.dumps(recall_memory(), ensure_ascii=False))
            continue

        answer, backend = agent.ask(prompt)

        console.print()
        console.print(
            Markdown(answer)
        )

        console.print(
            f"\n[dim]{backend}[/dim]\n"
        )


if __name__ == "__main__":
    main()
