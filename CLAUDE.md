# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based alert bot system for the Pinto DeFi protocol. It monitors blockchain events and disseminates information to Discord, Telegram, and Twitter channels. The project is forked from Beanstalk and maintains similar architecture for cross-compatibility.

## Development Commands

### Local Development
- Install dependencies: `pip3 install -r requirements.txt`
- Run a bot: `./dev.sh <module>` (e.g., `./dev.sh bots.discord_bot`)
- Debug with debugger: `./debug.sh <module>`
- Test specific transactions: `./dev.sh bots.discord_bot <comma-separated-tx-hashes>`
- Test seasons monitor: `./dev.sh bots.discord_bot seasons`

### Environment Setup
- Create `.env.dev` file with required environment variables
- The `dev.sh` script automatically loads environment variables and sets PYTHONPATH

### Docker Development
- Build: `docker/build.sh`
- Start: `docker/start.sh`
- Stop: `docker/stop.sh`
- See `docker/README.md` for detailed Docker instructions

## Architecture

### Core Components

1. **Bots** (`src/bots/`): Output channels for different platforms
   - `discord_bot.py` - Main Discord bot with event messaging
   - `telegram_bot.py` - Telegram event notifications
   - `twitter_bot.py` - Twitter hourly statistics
   - `discord_*_bot.py` - Status display bots (price, ETH, Basin)

2. **Monitors** (`src/monitors/`): Event detection and processing
   - `monitor.py` - Base monitor class with threading and error handling
   - `beanstalk.py` - Protocol-specific event monitoring
   - `market.py` - Market activity monitoring
   - `well.py` - Basin/Well liquidity monitoring
   - `seasons.py` - Season statistics monitoring

3. **Data Access** (`src/data_access/`): Blockchain and API integration
   - `contracts/` - Smart contract interaction utilities
   - `subgraphs/` - GraphQL subgraph queries
   - `etherscan.py` - Etherscan API integration

4. **Constants** (`src/constants/`): Configuration and addresses
   - `config.py` - Core configuration, RPC URLs, timing constants
   - `addresses.py` - Smart contract addresses
   - `channels.py` - Discord/Telegram channel configurations
   - `abi/` - Contract ABI files

### Key Design Patterns

- **Monitor Pattern**: Each monitor runs in its own thread with exponential backoff error recovery
- **Channel Abstraction**: Monitors can send to multiple output channels (Discord, Telegram, Twitter)
- **Dry Run Mode**: Test with specific transaction hashes or predefined scenarios
- **Environment-based Configuration**: Production vs development behavior controlled by environment variables

### Important Technical Details

- **Python Version**: Requires Python 3.8+ for proper exception logging
- **Web3 Integration**: Uses web3.py v5.31.4 for blockchain interaction
- **GraphQL**: Uses gql[aiohttp] for subgraph queries
- **Bot Libraries**: discord.py 1.7, pyTelegramBotAPI 4.0, tweepy 4.13.0

### Environment Variables

Key environment variables (set in `.env.dev`):
- `RPC_URL` - Ethereum RPC endpoint
- `ENS_RPC_URL` - ENS resolution endpoint
- Various bot tokens and API keys for Discord, Telegram, Twitter

### Testing and Debugging

- Use `DRY_RUN` environment variable to test with specific transactions
- Set `DRY_RUN="all"` to run through entire dry run collection
- Set `DRY_RUN="seasons"` to trigger seasons monitor
- Debug port 5678 available when using `debug.sh`

## Development Guidelines

- Follow the existing monitor pattern when creating new monitors
- Use the base `Monitor` class for consistent threading and error handling
- Maintain cross-compatibility with the original Beanstalk repository structure
- Test with dry run mode before deploying to production
- Use environment variables for configuration rather than hardcoded values