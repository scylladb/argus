#!/usr/bin/env python3
from werkzeug.middleware.profiler import ProfilerMiddleware
from argus_backend import start_server


argus_app = start_server()
argus_app.wsgi_app = ProfilerMiddleware(
    app=argus_app.wsgi_app,
    profile_dir="profile",
)

argus_app.run(
    host="0.0.0.0",
    port=5000,
    debug=True,
)
