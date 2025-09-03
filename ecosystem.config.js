module.exports = {
  apps : [{
    name   : "envelope-bot",
    script : "/home/ubuntu/LiveTradingBots/code/strategies/envelope/run.py",
    interpreter: "/home/ubuntu/LiveTradingBots/code/.venv/bin/python3",
    watch: false,
    autorestart: true,
    max_memory_restart: '200M'
  }]
};

