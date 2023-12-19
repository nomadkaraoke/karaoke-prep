import click
from karaoke_prep.finalise import karaoke_finalise


@click.command()
def main():
    """Command to finalise karaoke videos."""
    karaoke_finalise()


if __name__ == "__main__":
    main()
