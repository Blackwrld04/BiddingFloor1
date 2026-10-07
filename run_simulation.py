import asyncio
import subprocess
import sys
import time
import os
import signal
import httpx
from dotenv import load_dotenv

load_dotenv()

from agent.main import run_agent

COORDINATOR_PORT = int(os.getenv("PORT", "8000"))
COORDINATOR_URL = f"http://127.0.0.1:{COORDINATOR_PORT}"

async def wait_for_coordinator():
    print("[*] Waiting for Auction Coordinator to boot...")
    for _ in range(25):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{COORDINATOR_URL}/api/v1/nodes", timeout=1.0)
                if res.status_code == 200:
                    print("[OK] Coordinator is ONLINE and accepting connections!")
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.4)
    return False

async def main():
    print("=" * 70)
    print("[INIT] LAUNCHING VELES HACK 2026 - CHALLENGE 4 TESTBED & ARENA")
    print(f"[HTTP] Dashboard & Coordinator : {COORDINATOR_URL}")
    print("=" * 70)

    # 1. Start uvicorn coordinator in subprocess
    coord_process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "coordinator.app:app",
            "--host", "0.0.0.0",
            "--port", str(COORDINATOR_PORT),
            "--log-level", "warning"
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:
        # 2. Wait for healthy response
        ready = await wait_for_coordinator()
        if not ready:
            print("[ERROR] Coordinator failed to initialize in time.")
            coord_process.terminate()
            return

        print("\n" + "=" * 70)
        print(f"[READY] ARENA WEB DASHBOARD IS LIVE AT: {COORDINATOR_URL}")
        print("   Open this URL in your browser to view the real-time bidding battle!")
        print("=" * 70 + "\n")

        # 3. Start the autonomous Smart Agent
        agent_task = asyncio.create_task(run_agent(
            coordinator_url=COORDINATOR_URL,
            strategy_name="team",
            node_id="edge_agent_smart_04",
            node_name="CognitiveSwarmBot (Champion)"
        ))

        await agent_task

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[!] Shutting down simulation...")
    finally:
        coord_process.terminate()
        try:
            coord_process.wait(timeout=2)
        except Exception:
            coord_process.kill()
        print("[OK] All processes cleanly stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited.")
