import time
import numpy as np
from services.scheduler.ml.ddpg_agent import DDPGAgent
from services.scheduler.ml.environment import SchedulingEnv
import os
import torch

def train():
    env = SchedulingEnv()
    state_dim = env.state_dim
    action_dim = env.action_dim
    max_action = 1.0

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training DDPG Agent on {device}...")
    
    agent = DDPGAgent(state_dim, action_dim, max_action, device=device)
    
    episodes = 200
    rewards_history = []
    
    for ep in range(episodes):
        state = env.reset()
        agent.noise.reset()
        episode_reward = 0
        done = False
        
        while not done:
            action = agent.select_action(state, add_noise=True)
            next_state, reward, done, _ = env.step(action)
            
            agent.replay_buffer.push(state, action, reward, next_state, done)
            
            agent.train()
            
            state = next_state
            episode_reward += reward
            
        rewards_history.append(episode_reward)
        
        if (ep + 1) % 10 == 0:
            avg_reward = np.mean(rewards_history[-10:])
            print(f"Episode {ep + 1}/{episodes} | Avg Reward (last 10): {avg_reward:.2f}")

    os.makedirs("models", exist_ok=True)
    torch.save(agent.actor.state_dict(), "models/ddpg_actor.pth")
    print("Training complete. Model saved to models/ddpg_actor.pth")

if __name__ == "__main__":
    train()
