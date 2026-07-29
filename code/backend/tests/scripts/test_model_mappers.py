from sqlalchemy.orm import configure_mappers


def test_sqlalchemy_mappers_configure() -> None:
    import app.models  # noqa: F401

    configure_mappers()
