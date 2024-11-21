[discord-badge]: https://img.shields.io/discord/1308123512216748105?label=Pinto%20Discord
[discord-url]: https://pinto.money/discord

# Pinto Alert Bots

[![Discord][discord-badge]][discord-url]

**Alerts upon events emitted by [Pinto](https://github.com/pintomoney/protocol).**

## Bots

Python bots that disseminate various information to the Pinto Discord, Telegram, and Twitter accounts. 
- [Discord](https://pinto.money/discord)
- [Telegram (Events)](https://t.me/pintotracker)
- [Telegram (Announcements)](https://t.me/pintoannouncements)
- [Twitter](https://x.com/pintomoneybot)

Included in this repo is a set of bots that disseminate information to Pinto Telegram and Discord channels.
- **discord_bot** - Sends messages upon for various contract events, including swaps and protocol interactions.
- **telegram_bot** - Similar to discord_bot but for Telegram.
- **twitter_bot** - Similar to the above, but only sends hourly season stats.
- **discord_eth_bot** - Displays the current eth price and gas cost. Does not send messages.
- **discord_price_bot** - Displays the current Pinto price and other daily statistics. Does not send messages.
- **discord_basin_status_bot** - Displays current liquidity and trading information. Does not send messages.

Underlying each of these bots is a set of monitors. Each monitor is designed such that it is can serve multiple of these output channels.

This project is forked from Beanstalk. The original project can be found [here](https://github.com/BeanstalkFarms/Beanstalk-Py). The structure of this project is kept similar to the original - from a technical perspective this will allow either repository to benefit from future developments to the other. There are other bots in this repository that are unused by Pinto.

### Running locally
First, install the necessary requirements using `pip3.8 install -r requirements.txt`.

Create an `.env.dev` file using the provided example and place your varaibles there. Then, execute `./dev.sh <module>`. For example, to run the main set of bots, execute `./dev.sh bots.discord_bot`.

To test specific transaction(s), use `./dev.sh bots.discord_bot <txn hashes here>` with a list of comma separated hashes.

Bots can also be run in a docker container. See the docker directory for further information.

## License

[MIT](https://github.com/pinto-org/alerts/blob/main/LICENSE.txt)