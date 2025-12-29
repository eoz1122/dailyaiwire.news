import json
import os
from datetime import datetime
from pathlib import Path

class BudgetTracker:
    """Track Gemini API usage and enforce monthly budget caps"""
    
    def __init__(self, budget_file="budget_tracker.json", monthly_cap_usd=10.0):
        self.budget_file = budget_file
        self.monthly_cap = monthly_cap_usd
        # Gemini 2.5 Flash pricing (as of Dec 2024)
        self.cost_per_1k_input_tokens = 0.000075   # $0.075 per 1M tokens
        self.cost_per_1k_output_tokens = 0.0003    # $0.30 per 1M tokens
        self.load_usage()
    
    def load_usage(self):
        """Load usage data from file"""
        if os.path.exists(self.budget_file):
            with open(self.budget_file, 'r') as f:
                self.data = json.load(f)
                # Migration: Ensure breakdown exists
                if "breakdown" not in self.data:
                    self.data["breakdown"] = {}
        else:
            self.data = {
                "current_month": datetime.now().strftime("%Y-%m"),
                "total_spent": 0.0,
                "requests": 0,
                "tokens_used": 0,
                "breakdown": {}
            }
    
    def save_usage(self):
        """Save usage data to file"""
        with open(self.budget_file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def reset_if_new_month(self):
        """Reset counter if it's a new month"""
        current_month = datetime.now().strftime("%Y-%m")
        if self.data["current_month"] != current_month:
            print(f"📅 New month detected. Resetting budget tracker.")
            print(f"📊 Previous month ({self.data['current_month']}) spent: ${self.data['total_spent']:.4f}")
            self.data = {
                "current_month": current_month,
                "total_spent": 0.0,
                "requests": 0,
                "tokens_used": 0,
                "breakdown": {}
            }
            self.save_usage()
    
    def can_make_request(self, estimated_tokens=5000):
        """Check if we're under budget before making a request"""
        self.reset_if_new_month()
        
        # Estimate cost (conservative estimate)
        estimated_cost = (estimated_tokens / 1000) * self.cost_per_1k_input_tokens * 2
        projected_total = self.data["total_spent"] + estimated_cost
        
        if projected_total > self.monthly_cap:
            print(f"🚨 BUDGET CAP REACHED!")
            print(f"   Current spend: ${self.data['total_spent']:.4f}")
            print(f"   Monthly cap: ${self.monthly_cap:.2f}")
            print(f"   Requests this month: {self.data['requests']}")
            return False
        
        return True
    
    def log_request(self, input_tokens=0, output_tokens=0, category="Uncategorized"):
        """Log a completed API request with category tracking"""
        cost = (input_tokens / 1000 * self.cost_per_1k_input_tokens + 
                output_tokens / 1000 * self.cost_per_1k_output_tokens)
        
        self.data["total_spent"] += cost
        self.data["requests"] += 1
        self.data["tokens_used"] += (input_tokens + output_tokens)
        
        # Track category breakdown
        if category not in self.data["breakdown"]:
            self.data["breakdown"][category] = 0.0
        self.data["breakdown"][category] += cost
        
        self.save_usage()
        
        # Print status every 10 requests
        if self.data["requests"] % 10 == 0:
            self.print_status()
    
    def print_status(self):
        """Print current budget status with breakdown"""
        percentage = (self.data["total_spent"] / self.monthly_cap) * 100
        print(f"\n💰 Budget Status ({self.data['current_month']})")
        print(f"   Spent: ${self.data['total_spent']:.4f} / ${self.monthly_cap:.2f} ({percentage:.1f}%)")
        print(f"   Requests: {self.data['requests']}")
        print(f"   Tokens: {self.data['tokens_used']:,}")
        
        if self.data.get("breakdown"):
            print("   --- Cost Breakdown ---")
            # Sort by highest cost
            sorted_cats = sorted(self.data["breakdown"].items(), key=lambda x: x[1], reverse=True)
            for cat, amount in sorted_cats:
                cat_percent = (amount / self.data['total_spent']) * 100 if self.data['total_spent'] > 0 else 0
                print(f"   • {cat:<20}: ${amount:.4f} ({cat_percent:.1f}%)")

        if percentage > 80:
            print(f"   ⚠️  WARNING: {percentage:.1f}% of budget used!")
