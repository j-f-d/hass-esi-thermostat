# ESI WiFi Thermostat Home Assistant Integration

This is a custom Home Assistant integration for controlling ESI WiFi Thermostats. It allows you to manage ESI smart thermostats within Home Assistant, providing functionality for setting temperatures and configuring thermostat options.

## Features

- Fetch data from the ESI Thermostat API
- Control target temperature for thermostats
- Configure update frequency for thermostat data
- Easy to install and configure

## Installation

### 1. Clone or download the repository:

```bash
git clone https://github.com/DeclanSC/hass-esi-thermostat.git
```

### 2. Install the integration:
- Copy the esi_thermostat folder from this repository to your Home Assistant's custom components directory:
config/custom_components/esi_thermostat/
- Restart Home Assistant to load the new integration.

### 3. Configure the integration:
- Navigate to Configuration > Integrations in Home Assistant.
- Search for "ESI Thermostat."
- Enter your ESI account email and password.
- Optionally, configure the Scan Interval to determine how frequently the thermostat data is updated.

## Usage
Once the integration is configured, you can control the thermostat’s target temperature from the Home Assistant interface.

### Climate Entity
You will see a climate entity for each connected thermostat in the Climate section of Home Assistant. This entity allows you to:
- Set the target temperature.
- Monitor the current temperature.

### Troubleshooting
- **This integration has only been tested with 6 Series thermostats so may not work as expected for other models**
- If the integration doesn't work after installation, check the Home Assistant logs for errors.
- Ensure that your ESI credentials are correct.
- If you're receiving Authentication Failed errors, double-check your email and password.

## Contributing
Feel free to fork this repository and submit issues or pull requests. Contributions are always welcome!

