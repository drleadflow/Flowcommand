#!/usr/bin/env python3
"""
OpenClaw Sub-Agent Delegation Router
Hermes -> OpenClaw Agents (Gary, Patty, Blaze, Ron, Codey)

Usage:
  python3 openclaw_delegate.py "write a welcome email" "context: med spa client"
  python3 openclaw_delegate.py --agent gary "subject line for flash sale"
  python3 openclaw_delegate.py --workflow launch_campaign "new crypto tax service"
"""

import argparse
import yaml
import subprocess
import sys
import re
import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# Paths
AGENTS_CONFIG = Path.home() / ".hermes" / "openclaw_agents.yaml"
OPENCLAW_DIR = Path.home() / ".openclaw"
OPENCLAW_AGENTS_DIR = OPENCLAW_DIR / "agents"


def load_agents_config() -> Dict:
    """Load agent registry from YAML."""
    if not AGENTS_CONFIG.exists():
        print(f"Error: Config not found at {AGENTS_CONFIG}", file=sys.stderr)
        sys.exit(1)
    
    with open(AGENTS_CONFIG, 'r') as f:
        return yaml.safe_load(f)


def create_openclaw_agent(agent_key: str, agent_config: Dict) -> bool:
    """Create a new OpenClaw agent using CLI command."""
    agent_name = agent_key
    
    # Map base_agent to actual model
    base_agent = agent_config.get('base_agent', 'claude-code')
    model_map = {
        'claude-code': 'anthropic/claude-sonnet-4-6',
        'sonnet': 'anthropic/claude-sonnet-4-6',
        'opus': 'anthropic/claude-opus-4-6',
        'gpt4': 'openai/gpt-4o',
        'cowgirlcourtney': 'anthropic/claude-sonnet-4-6',
        'topeops': 'anthropic/claude-sonnet-4-6',
        'bleutech': 'anthropic/claude-sonnet-4-6',
    }
    model = model_map.get(base_agent, 'anthropic/claude-sonnet-4-6')
    
    # Create workspace directory
    agent_workspace = OPENCLAW_AGENTS_DIR / f"{agent_name}_workspace"
    agent_workspace.mkdir(parents=True, exist_ok=True)
    
    # Create IDENTITY.md in workspace/agent folder
    agent_dir = agent_workspace / "agent"
    agent_dir.mkdir(exist_ok=True)
    
    identity_content = f"""# {agent_config.get('name', agent_key)}

{agent_config.get('role', 'AI Agent')}

{agent_config.get('description', '')}

## Base Agent
{base_agent}

## Created By
Hermes OpenClaw Delegation Router
"""
    
    with open(agent_dir / "IDENTITY.md", 'w') as f:
        f.write(identity_content)
    
    # Use openclaw CLI to register the agent
    cmd = [
        'openclaw', 'agents', 'add',
        '--non-interactive',
        '--model', model,
        '--workspace', str(agent_workspace),
        '--agent-dir', str(agent_dir),
        agent_name
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            # Agent might already exist or other error
            if "already exists" in result.stderr.lower():
                print(f"  Agent '{agent_name}' already registered", file=sys.stderr)
                return True
            print(f"  Error creating agent: {result.stderr}", file=sys.stderr)
            # Continue anyway - agent files are set up
        else:
            print(f"  Created OpenClaw agent: {agent_name} (model: {model})", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  Warning: CLI agent creation failed: {e}", file=sys.stderr)
        # Continue anyway - agent files are set up
        return True


def openclaw_agent_exists(agent_name: str) -> bool:
    """Check if an OpenClaw agent already exists via CLI."""
    try:
        result = subprocess.run(
            ['openclaw', 'agents', 'list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Parse output for agent name
            return f"- {agent_name}" in result.stdout or f"- {agent_name} " in result.stdout
    except:
        pass
    
    # Fallback: check directory
    agent_dir = OPENCLAW_AGENTS_DIR / agent_name
    return agent_dir.exists()


def ensure_agent_exists(agent_key: str, agent_config: Dict) -> bool:
    """Ensure the OpenClaw agent exists, creating it if necessary."""
    if openclaw_agent_exists(agent_key):
        return True
    
    print(f"  Agent '{agent_key}' not found. Creating...", file=sys.stderr)
    return create_openclaw_agent(agent_key, agent_config)


def spawn_agent_process(agent_key: str, task: str, context: str, config: Dict) -> str:
    """Spawn an agent process using openclaw agent CLI with --agent flag."""
    agent = config['agents'].get(agent_key)
    if not agent:
        return f"Error: Agent '{agent_key}' not found in config"
    
    # Ensure agent exists (creates if needed)
    if not ensure_agent_exists(agent_key, agent):
        return f"Error: Failed to create agent '{agent_key}'"
    
    # Load skills context
    skills_context = build_skills_context(agent, config)
    
    # Build full prompt with system identity
    full_prompt = f"""{agent.get('prompt_prefix', '')}{skills_context}

TASK: {task}

{f"CONTEXT: {context}" if context else ""}

Execute this task as {agent['name']}, the {agent['role']}. 
Reference your available skills when relevant.
Be concise. Return only the deliverable, no fluff."""
    
    # Use openclaw agent with --agent flag to route to specific agent
    cmd = [
        'openclaw', 'agent',
        '--agent', agent_key,
        '--message', full_prompt,
        '--json'
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 min timeout
        )
        
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Handle known fallback messages (agent not found falls back to default)
            if "falling back" in stderr.lower() or "unknown agent" in stderr.lower():
                # Try again with local mode as fallback
                return run_local_agent(agent_key, agent, full_prompt)
            return f"Error from OpenClaw: {stderr}"
        
        return result.stdout
    
    except subprocess.TimeoutExpired:
        return "Error: Agent timed out after 5 minutes"
    except FileNotFoundError:
        return "Error: 'openclaw' CLI not found. Is OpenClaw installed and in PATH?"
    except Exception as e:
        return f"Error spawning agent: {str(e)}"


def run_local_agent(agent_key: str, agent: Dict, full_prompt: str) -> str:
    """Fallback: Run agent in local mode with embedded model."""
    base_agent = agent.get('base_agent', 'claude-code')
    model_map = {
        'claude-code': 'anthropic/claude-sonnet-4-6',
        'sonnet': 'anthropic/claude-sonnet-4-6',
        'opus': 'anthropic/claude-opus-4-6',
        'gpt4': 'openai/gpt-4o',
    }
    model = model_map.get(base_agent, 'anthropic/claude-sonnet-4-6')
    
    cmd = [
        'openclaw', 'agent',
        '--local',
        '--model', model,
        '--message', full_prompt,
        '--json'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return f"Error (local fallback): {result.stderr}"
        return result.stdout
    except Exception as e:
        return f"Error in local fallback: {str(e)}"


def calculate_match_score(task: str, keywords: List[str]) -> float:
    """Calculate how well task matches agent keywords."""
    task_lower = task.lower()
    words = set(re.findall(r'\b\w+\b', task_lower))
    
    matches = 0
    for keyword in keywords:
        keyword_lower = keyword.lower()
        # Direct substring match
        if keyword_lower in task_lower:
            matches += 1
        # Word-level match
        elif keyword_lower in words:
            matches += 1
    
    return matches / len(keywords) if keywords else 0


def route_task(task: str, config: Dict) -> Tuple[str, float]:
    """
    Route task to best-matching agent.
    Returns: (agent_key, confidence_score)
    """
    agents = config.get('agents', {})
    scores = []
    
    for key, agent in agents.items():
        score = calculate_match_score(task, agent.get('keywords', []))
        scores.append((key, score, agent['name']))
    
    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    
    if not scores or scores[0][1] == 0:
        # No match, return default
        default = config.get('default_agent', 'gary')
        return default, 0.0
    
    return scores[0][0], scores[0][1]


def load_skill_content(skill_name: str, skill_repo: str) -> Optional[str]:
    """Load SKILL.md content for a given skill from the repo."""
    import os
    
    # Expand tilde in path
    skill_repo = os.path.expanduser(skill_repo)
    skill_path = Path(skill_repo) / "skills" / skill_name / "SKILL.md"
    
    if not skill_path.exists():
        return None
    
    try:
        with open(skill_path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"[Error loading skill: {e}]"


def build_skills_context(agent: Dict, config: Dict) -> str:
    """Build skills reference section for agent prompt."""
    skills = agent.get('skills', [])
    skill_repo = config.get('skill_repo', '~/marketingskills')
    
    if not skills:
        return ""
    
    context_parts = ["\n\n=== AVAILABLE SKILLS ===", 
                     "You have access to these specialized marketing skills:", ""]
    
    for skill in skills:
        content = load_skill_content(skill, skill_repo)
        if content:
            # Extract just the header and key sections to keep prompt size manageable
            lines = content.split('\n')
            skill_context = [f"\n--- {skill} ---"]
            
            # Get description from frontmatter
            in_frontmatter = False
            frontmatter_started = False
            for line in lines[:30]:  # Check first 30 lines
                if line.strip() == '---':
                    if not frontmatter_started:
                        frontmatter_started = True
                        in_frontmatter = True
                    else:
                        in_frontmatter = False
                elif in_frontmatter and 'description:' in line:
                    skill_context.append(line.strip())
            
            # Add quick reference to full file
            skill_path = f"~/marketingskills/skills/{skill}/SKILL.md"
            skill_context.append(f"Full skill file: {skill_path}")
            
            context_parts.extend(skill_context)
    
    context_parts.append("\nUse these frameworks when relevant to the task.")
    return '\n'.join(context_parts)


def execute_openclaw(agent_key: str, task: str, context: str, config: Dict) -> str:
    """Execute task via OpenClaw CLI - spawns real agent process."""
    return spawn_agent_process(agent_key, task, context, config)


def run_workflow(workflow_name: str, task_input: str, config: Dict) -> str:
    """Execute a multi-agent workflow."""
    workflows = config.get('workflows', {})
    workflow = workflows.get(workflow_name)
    
    if not workflow:
        available = ', '.join(workflows.keys())
        return f"Error: Workflow '{workflow_name}' not found. Available: {available}"
    
    results = []
    results.append(f"🔄 Running workflow: {workflow.get('description', workflow_name)}\n")
    
    context_accumulator = f"Original goal: {task_input}\n\n"
    
    for i, step in enumerate(workflow.get('steps', []), 1):
        agent_key = step['agent']
        step_task = step['task']
        
        agent = config['agents'].get(agent_key, {})
        agent_name = agent.get('name', agent_key)
        agent_icon = agent.get('icon', '🤖')
        
        results.append(f"\n--- Step {i}: {agent_icon} {agent_name} ---")
        results.append(f"Task: {step_task}")
        
        # Execute with accumulated context
        full_task = f"{step_task}\n\nPrevious context:\n{context_accumulator}"
        output = execute_openclaw(agent_key, full_task, "", config)
        
        results.append(f"Output:\n{output}")
        context_accumulator += f"\n[{agent_name}] {output[:500]}...\n"
    
    return '\n'.join(results)


def main():
    parser = argparse.ArgumentParser(
        description='Route tasks from Hermes to OpenClaw agents'
    )
    parser.add_argument('task', nargs='?', default='', help='The task description')
    parser.add_argument('context', nargs='?', default='', help='Additional context')
    parser.add_argument('--agent', '-a', help='Force specific agent (gary, patty, blaze, ron, codey)')
    parser.add_argument('--workflow', '-w', help='Run a predefined workflow')
    parser.add_argument('--list', '-l', action='store_true', help='List available agents')
    parser.add_argument('--dry-run', '-d', action='store_true', help='Show routing decision without executing')
    
    args = parser.parse_args()
    
    # Load config
    config = load_agents_config()
    
    # List mode
    if args.list:
        print("Available Agents:")
        for key, agent in config.get('agents', {}).items():
            print(f"  {agent.get('icon', '🤖')} {key}: {agent['name']} - {agent['role']}")
            skills = agent.get('skills', [])
            if skills:
                print(f"     Skills: {', '.join(skills[:5])}{'...' if len(skills) > 5 else ''}")
        print(f"\nDefault: {config.get('default_agent', 'gary')}")
        print("\nWorkflows:")
        for key, wf in config.get('workflows', {}).items():
            print(f"  {key}: {wf.get('description', 'No description')}")
            steps = wf.get('steps', [])
            step_str = ' → '.join([s['agent'] for s in steps])
            print(f"     Flow: {step_str}")
        return 0
    
    # Check for required task if not listing
    if not args.task:
        parser.error("task is required (unless using --list)")
    
    # Workflow mode
    if args.workflow:
        result = run_workflow(args.workflow, args.task, config)
        print(result)
        return 0

    # Single task delegation
    if args.agent:
        agent_key = args.agent.lower()
        confidence = 1.0  # Forced
    else:
        agent_key, confidence = route_task(args.task, config)

    agent = config['agents'].get(agent_key, {})

    # Check confidence threshold
    threshold = config.get('confidence_threshold', 0.6)
    if confidence < threshold and not args.agent:
        print(f"⚠️  Low confidence match ({confidence:.2f}) for agent '{agent_key}'")
        print(f"   Task: {args.task[:60]}...")
        print(f"   Suggestion: Use --agent to specify, or rephrase task.")
        return 1

    if args.dry_run:
        print(f"Would route to: {agent.get('icon', '🤖')} {agent.get('name', agent_key)}")
        print(f"Confidence: {confidence:.2f}")
        print(f"Base agent: {agent.get('base_agent', 'claude-code')}")
        skills = agent.get('skills', [])
        if skills:
            print(f"Skills loaded: {', '.join(skills)}")
        return 0
    
    # Execute
    print(f"🎯 Delegating to {agent.get('icon', '🤖')} {agent.get('name', agent_key)}...")
    result = execute_openclaw(agent_key, args.task, args.context, config)
    print(f"\n{result}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
