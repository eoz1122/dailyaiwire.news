import json
import os
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger('budget')

class BudgetTracker:
    """Track Gemini API usage and enforce monthly budget caps"""
    
    def __init__(self, budget_file="budget_tracker.json", monthly_cap_usd=10.0):
        self.budget_file = budget_file
        self.monthly_cap = monthly_cap_usd
        # Gemini 1.5 Flash pricing (Standard Rate)
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
        """Save usage data to file atomically to prevent corruption"""
        temp_file = f"{self.budget_file}.tmp"
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            # Atomic rename (works on Unix, on Windows requires os.replace)
            os.replace(temp_file, self.budget_file)
        except Exception as e:
            logger.error("❌ Error saving budget usage: %s", e)
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    def reset_if_new_month(self):
        """Reset counter if it's a new month"""
        current_month = datetime.now().strftime("%Y-%m")
        if self.data["current_month"] != current_month:
            logger.info("📅 New month detected. Resetting budget tracker.")
            logger.info("📊 Previous month (%s) spent: $%.4f", self.data['current_month'], self.data['total_spent'])
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
        self.reset_if_new_day() # Reset daily counter if needed
        
        # Estimate cost (conservative estimate)
        estimated_cost = (estimated_tokens / 1000) * self.cost_per_1k_input_tokens * 2
        projected_total = self.data["total_spent"] + estimated_cost
        
        # 1. Check Monthly Cap
        if projected_total > self.monthly_cap:
            logger.warning("🚨 MONTHLY BUDGET CAP REACHED!")
            logger.warning("   Current spend: $%.4f", self.data['total_spent'])
            logger.warning("   Monthly cap: $%.2f", self.monthly_cap)
            return False
            
        # 2. Check Daily Safety Cap ($1.50/day hard limit)
        daily_cap = 1.50
        projected_daily = self.data.get("daily_spent", 0.0) + estimated_cost
        if projected_daily > daily_cap:
             logger.warning("🚨 DAILY SPEND LIMIT REACHED ($%s)!", daily_cap)
             logger.warning("   Today's spend: $%.4f", self.data['daily_spent'])
             return False
        
        return True

    def reset_if_new_day(self):
        """Reset daily tracking if it's a new day"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.data.get("current_day") != today:
            logger.info("📅 New day detected (%s). Resetting daily tracker.", today)
            self.data["current_day"] = today
            self.data["daily_spent"] = 0.0
            self.save_usage()
    
    def log_request(self, input_tokens=0, output_tokens=0, category="Uncategorized"):
        """Log a completed API request with category tracking (Atomic Refresh)"""
        # Reload to ensure we have latest data from other processes
        self.load_usage()
        self.reset_if_new_month()
        
        cost = (input_tokens / 1000 * self.cost_per_1k_input_tokens + 
                output_tokens / 1000 * self.cost_per_1k_output_tokens)
        
        self.data["total_spent"] += cost
        self.data["daily_spent"] = self.data.get("daily_spent", 0.0) + cost
        self.data["requests"] += 1
        self.data["tokens_used"] += (input_tokens + output_tokens)
        
        # Ensure breakdown exists
        if "breakdown" not in self.data:
            self.data["breakdown"] = {}
            
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
        logger.info("💰 Budget Status (%s)", self.data['current_month'])
        logger.info("   Spent: $%.4f / $%.2f (%.1f%%)", self.data['total_spent'], self.monthly_cap, percentage)
        logger.info("   Requests: %d", self.data['requests'])
        logger.info("   Tokens: %s", f"{self.data['tokens_used']:,}")
        
        if self.data.get("breakdown"):
            logger.info("   --- Cost Breakdown ---")
            # Sort by highest cost
            sorted_cats = sorted(self.data["breakdown"].items(), key=lambda x: x[1], reverse=True)
            for cat, amount in sorted_cats:
                cat_percent = (amount / self.data['total_spent']) * 100 if self.data['total_spent'] > 0 else 0
                logger.info("   • %-20s: $%.4f (%.1f%%)", cat, amount, cat_percent)

        if percentage > 80:
            logger.warning("   ⚠️  WARNING: %.1f%% of budget used!", percentage)
