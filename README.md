# ESI WiFi Thermostat Home Assistant Integration

This is a custom integration for Home Assistant that adds support for control of ESI WiFi Thermostats. It enables temperature management and thermostat configuration directly within Home Assistant. This version attempts to follow best practices more closely for the development of HACS integrations.

To that end I have developed a PyPI module called [esi-controls-async] in line with the Home Assistant docs for [Building a Python library for an API] which is used by this integration.

## Known Supported Devices

- **[ESCTP5-W]** Programmable Cylinder Thermostat as a Water Heater device

## Untested included Devices

- **[ESRTP6B]** Series 6 WiFi Programmable Room Thermostat (derived from Declan's repo.)

## Additional or Broken Devices

I have attempted to include support for the **[ESRTP6B]** device, but due to the lack of hardware, I cannot test it. Similar devices, such as the **[ESRTP5WF]** or **[ESRTP6CW]** are likely to be detected, but may or may not work. If you encounter a working device, please let me know as an issue to update this document. If you have this or another similar room or hot water cylinder thermostats, I'm happy to help get it working. Please start by creating an issue, along with the log messages indicating a problem.

## Features

Compared to DeclanSC's version, I have:

- Added support for Cylinder Thermostats (as a Water Heater)
- Replaced any use of synchronous IO with Asynchronous
- Addressed all pyline and coding standards issues.
- Reviewed and rewritten the API to conform to the documented recommendations.

The common features are:

- Retrieve data from the ESI Thermostat, via the Web API
- Set target temperatures for thermostats
- Change thermostat modes, between Auto, Off and Manual.
- Configure update intervals for thermostat data
- Simple installation and configuration

## HACS Installation

<!-- Just click here to directly go to the repository in HACS and click "Download":

[![hacs-default](https://img.shields.io/badge/HACS-Default-blue.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=j-f-d&repository=hass-esi-thermostat&category=integrations)

Or: -->

- Open HACS
- Click the three dots in the top right
- Select Custom Repositories
- Paste <https://github.com/j-f-d/hass-esi-thermostat> as the repository name
- Select Integration for the type

## Manual Installation

### 1. Download the repository

Clone the repository or download it as a ZIP file:

```bash
git clone https://github.com/j-f-d/hass-esi-thermostat.git
```

### 2. Install the integration

Copy the esi_thermostat folder to your Home Assistant custom_components directory:

> config/custom_components/esi_thermostat/

Restart Home Assistant to load the integration.

### 3. Configure the integration

1. In Home Assistant, navigate to **Settings** > **Devices and services** > **Add Integration**
2. Search for **ESI Thermostat**
3. Enter your ESI account email and password, as used for the ESI Centro App
4. Optionally, change the refresh interval to control how frequently the thermostat data is updated

## Usage

Once configured, a climate entity will be created for each connected room thermostat, or a water heater entity for each programmable cyclinder thermostat. These entities allow you to:

- Set the target temperature
- Monitor the current temperature
- Change thermostat modes

If the thermostat goes offline, it will appear as 'Unavailable' to Home Asssistant.

The thermostat documentation refers to three main modes of operation, 'Off', 'Manual' and 'Auto' in addition to 'Boost', 'Holiday' and 'Sterilise' modes. This integration uses 'Manual' for the HASS 'on' mode.

If 'Boost' is attempted from either 'Auto' or 'Manual' mode either at the device or via the ESI Centro app, these are treated as 'on' mode by the integration, which will show the boosted temperature as the target.

When in 'off' mode, this water heater integration doesn't report a target temperature, resulting in a gap when you look at the history graphs. (This is a change in behaviour from earlier versions, which would report a target temperature, even though it might not really be the active target.)

When transitioning to 'on' mode, this water heater integration attempts to restore the last target temperature which has been read in either 'on' or 'auto' mode.

Setting a target temperature causes a transition to the 'on' mode if the thermostat was previously operating in another mode.

Although it is possible to transition to auto mode, there is no way to examine or change the schedules using this integration.

**_Holiday and Sterilise Modes are currently untested._**

## Notes and Troubleshooting

- This integration adds support for and has been tested with the **[ESCTP5-W]** programmable cylinder thermostat.
- It is derived from work to support **ESI 6 Series** thermostats, so it is hoped, but untested that they still work.
- Other detected devices will appear as climate entities by default. Until explicitly supported, the cylinder thermostat didn't 'just work' so that is likely the case for other devices too.
- If the integration does not function as expected, check the Home Assistant logs for errors.
- Verify that your ESI credentials are correct.
- If you encounter authentication errors, ensure that your email and password are entered correctly and match those used for the ESI Centro app.

## Contributing

Contributions are welcome. Feel free to fork the repository and submit issues or pull requests.

[ESCTP5-W]: <https://support.esicontrols.co.uk/product/esctp5-w>
[ESRTP5WF]: <https://support.esicontrols.co.uk/product/esrtp5wifi>
[ESRTP6B]: <https://support.esicontrols.co.uk/product/stratus-esrtp6b>
[ESRTP6CW]: <https://support.esicontrols.co.uk/product/esrtp6c/>
[esi-controls-async]: <https://pypi.org/project/esi-controls-async/>
[Building a Python library for an API]: <https://developers.home-assistant.io/docs/api_lib_index>