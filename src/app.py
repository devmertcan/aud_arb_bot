# Optional: not required by our CLI, but helpful if you want to launch dash alone
from io.dashboard_api import make_app
def app():
    # dummy app (no live stream without the engine)
    return make_app(lambda n: [], lambda q: lambda: None)
