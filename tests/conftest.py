import os

# Never let a developer's real .env (WorkOS keys etc.) change how the tests run.
os.environ["AGENTGUARD_SKIP_DOTENV"] = "1"
