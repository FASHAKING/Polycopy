from polycopy.core.config import Settings


def test_cors_origin_list_parses_csv():
    s = Settings(cors_origins="https://a.com, https://b.com ,")
    assert s.cors_origin_list == ["https://a.com", "https://b.com"]


def test_cors_wildcard():
    assert Settings(cors_origins="*").cors_origin_list == ["*"]


def test_dev_has_no_secret_problems():
    s = Settings(app_env="dev", app_secret="change-me", fernet_key="")
    assert s.check_production_secrets() == []


def test_prod_flags_insecure_defaults():
    s = Settings(app_env="prod", app_secret="change-me", fernet_key="", cors_origins="*")
    problems = s.check_production_secrets()
    assert any("APP_SECRET" in p for p in problems)
    assert any("FERNET_KEY" in p for p in problems)
    assert any("CORS" in p for p in problems)


def test_prod_clean_config_has_no_problems():
    s = Settings(
        app_env="prod",
        app_secret="a-long-random-secret",
        fernet_key="some-key",
        cors_origins="https://app.example.com",
    )
    assert s.check_production_secrets() == []
