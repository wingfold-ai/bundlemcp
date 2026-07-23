from bundlemcp.schemas import BundleUpsert


class BootstrapBundle(BundleUpsert):
    servers: list[str] = []  # member server names (BND-6)
