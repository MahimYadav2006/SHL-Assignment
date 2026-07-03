import sys

def rewrite():
    with open("agent.py", "r") as f:
        lines = f.readlines()
    
    with open("agent.py", "w") as f:
        for i, line in enumerate(lines):
            idx = i + 1
            if 119 <= idx <= 204:
                continue
            if 212 <= idx <= 218:
                continue
            if 238 <= idx <= 264:
                continue
            f.write(line)

rewrite()
