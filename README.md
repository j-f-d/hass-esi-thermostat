# ESI WiFi Thermostat Home Assistant Integration

This is a custom integration for Home Assistant that adds support for controlling ESI WiFi Thermostats. It enables temperature management and thermostat configuration directly within Home Assistant.

## Features

- Retrieve data from the ESI Thermostat API
- Set target temperatures for thermostats
- Configure update intervals for thermostat data
- Simple installation and configuration

## HACS Installation

Just click here to directly go to the repository in HACS and click "Download":

[![hacs-default](https://img.shields.io/badge/HACS-Default-blue.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=DeclanSC&repository=esi-thermostat&category=integration)

Or:

- Open HACS
- Search for "ESI Thermostat"
- Click "Download" button and install repository in HACS

## Manual Installation

### 1. Download the repository

Clone the repository or download it as a ZIP file:

```bash
git clone https://github.com/DeclanSC/hass-esi-thermostat.git
```

### 2. Install the integration

Copy the esi_thermostat folder to your Home Assistant custom_components directory:

> config/custom_components/esi_thermostat/

Restart Home Assistant to load the integration.

### 3. Configure the integration

1. In Home Assistant, navigate to **Settings** > **Devices and services** > **Add Integration**
2. Search for **ESI Thermostat**
3. Enter your ESI account email and password
4. Optionally, set the refresh interval to control how frequently the thermostat data is updated

## Usage

Once configured, a climate entity will be created for each connected thermostat. These entities allow you to:

- Set the target temperature
- Monitor the current temperature

## Notes and Troubleshooting

- This integration has been tested with **ESI 6 Series** thermostats. Other models may not be supported.
- If the integration does not function as expected, check the Home Assistant logs for errors.
- Verify that your ESI credentials are correct.
- If you encounter authentication errors, ensure that your email and password are entered correctly.

## Contributing

Contributions are welcome. Feel free to fork the repository and submit issues or pull requests.
