# ESI WiFi Thermostat Home Assistant Integration

This is a custom integration for Home Assistant that adds support for control of ESI WiFi Thermostats. It enables temperature management and thermostat configuration directly within Home Assistant. This version attempts to follow [the rules] more closely for the development of HASS integrations.

To that end I have developed a PyPI module called [esi-controls-async] in line with the Home Assistant docs for [Building a Python library for an API] which is used by this integration.

Before using the configuration, you should set up your thermostats and give them names using the [ESI Centro App]. This creates an association in the ESI cloud servers between the device id and the name by which you identify the device, which is used by the integration. The device name can be changed in the [ESI Centro App] from the "Device setting" page and will be reflected in HASS after an integration reload.

## Known Supported Devices

- **[ESCTP5-W]** Programmable Cylinder Thermostat as a Water Heater device

## Untested included Devices

- **[ESRTP6B]** Series 6 WiFi Programmable Room Thermostat (derived from [DeclanSC's repo].)

## Additional or Broken Devices

I have attempted to include support for the **[ESRTP6B]** device, but due to the lack of hardware, I cannot test it. Similar devices, such as the **[ESRTP5WF]** or **[ESRTP6CW]** are likely to be detected, but may or may not work. If you encounter a working device, please let me know as an issue to update this document. If you have this or another similar room or hot water cylinder thermostats, I'm happy to help get it working. Please start by creating an issue, along with the log messages indicating a problem.

## Features

Compared to [DeclanSC's repo], I have:

- Added support for Cylinder Thermostats (as a Water Heater)
- Replaced any use of synchronous IO with Asynchronous
- Addressed all Pylint/Pylance and coding standards issues.
- Reviewed and rewritten the API to conform to more of [the rules].

The common features are:

- Retrieve data from the ESI Thermostat, via the Web API
- Set target temperatures for thermostats
- Change thermostat modes, between Auto, Off and Manual.
- Configure update intervals for thermostat data
- Simple installation and configuration

## Installation

### Downloading the integration using [HACS]

<!-- Just click here to directly go to the repository in HACS and click "Download":

[![hacs-default](https://img.shields.io/badge/HACS-Default-blue.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=j-f-d&repository=hass-esi-thermostat&category=integrations)

Or: -->

1. Open [HACS]
2. Click/Touch the three dots in the top right, select: "Custom Repositories"
    1. Paste <https://github.com/j-f-d/hass-esi-thermostat> as the repository name
    2. Select "Integration" for the type
    3. Close the pop-up, "ESI Thermostat (JFD)" should now be in the "Available for download" list
5. Select the "ESI Thermostat (JFD)" integration and press the "Download" icon.

### Manual integration download

#### 1. Clone the repository to a local directory

Clone the repository or download it as a ZIP file:

```bash
git clone https://github.com/j-f-d/hass-esi-thermostat.git
```

#### 2. Make it available to HASS

Copy or link the esi_thermostat folder to your Home Assistant custom_components directory:

```bash
$ ln -s hass-esi-thermostat/custom_components/esi_thermostat /workspaces/hass-core/config/config/custom_components/esi_thermostat
```

Using a symbolic link, as above, facilitates easily pulling updates into a docker container running hass-core, e.g. for testing branches in advance of release or for submitting a pull request.

Restart Home Assistant to load the integration.

### Adding and Configuring the ESI Thermostat Integration

After downloading, as for other integrations, this integration must be added and configured.

1. In Home Assistant, navigate to **Settings** > **Devices and services** > **Add Integration**
2. Search for **ESI Thermostat (JFD)**
3. Enter your ESI account email and password[^1], as used for the [ESI Centro App]
4. Optionally, change the refresh interval to control how frequently the thermostat data is updated

[^1]: The credentials are held within your HASS instance as part of the integration configuration and are only used via an **https** connection to the ESI servers to obtain an authorisation key when necessary.

## Usage

Once configured, a climate entity will be created for each connected room thermostat, or a water heater entity for each programmable cyclinder thermostat. These entities allow you to:

- Set the target temperature
- Monitor the current temperature
- Change thermostat modes

If the thermostat goes offline, it will appear as 'Unavailable' to Home Asssistant.

The thermostat documentation refers to three main modes of operation, 'Off', 'Manual' (or 'MAN') and 'Auto' in addition to 'Boost', 'Holiday' and 'Sterilise' modes. This integration uses 'Manual' for the HASS 'on' mode and 'Off' for the HASS 'off' mode.

If 'Boost' is attempted from either 'Auto' or 'Manual' mode either at the device or via the [ESI Centro app], these are treated as 'on' mode by the integration, which will show the boosted temperature as the target.

When in 'off' mode, this water heater integration doesn't report a target temperature, resulting in a gap when you look at the history graphs. (This is a change in behaviour from earlier versions, which would report a target temperature, even though it might not really be the active target.)

When transitioning to 'on' mode, this water heater integration attempts to restore the last target temperature which has been read in either 'on' or 'auto' mode.

Setting a target temperature causes a transition to the 'on' mode if the thermostat was previously operating in another mode.

Although it is possible to transition to auto mode, there is no way to examine or change the schedules using this integration.

**_Modes such as Holiday, Boost and Sterilise are not well tested, because HASS does that sort of work for me. If set using the termostat directly or the [ESI Centro App], they should result in the thermostat state appearing Off or Manual, or Auto or as appropriate. HASS has no concept of what the thermostat's schedule would be when set manually or via the app._**

For scheduling, I recommend Niels Faber's [Scheduler Component] and [Lovelace Scheduler Card]

## Notes and Troubleshooting

- This integration adds support for and has been tested with the **[ESCTP5-W]** programmable cylinder thermostat.
- It is derived from work to support **ESI 6 Series** thermostats, so it is hoped, but untested that they still work.
- Other detected devices will appear as climate entities by default. Until explicitly supported, the cylinder thermostat didn't 'just work' so that is likely the case for other devices too.
- If the integration does not function as expected, check the Home Assistant logs for errors.
- If that shows authentication errors, verify that your email and password are entered correctly and match those used for the [ESI Centro app] and work at the [ESI Portal Heating History dashboard]. If you can't log in to that dashboard, then this integration won't work.

## Contributing

Contributions are welcome. Feel free to fork the repository and submit issues or pull requests.

[DeclanSC's repo]: <https://github.com/DeclanSC/hass-esi-thermostat>
[the rules]: <https://developers.home-assistant.io/docs/core/integration-quality-scale/rules>
[HACS]: <https://www.hacs.xyz/docs/use/configuration/basic/#setting-up-the-hacs-integration>
[Scheduler Component]: <https://github.com/nielsfaber/scheduler-component>
[Lovelace Scheduler Card]: <https://github.com/nielsfaber/scheduler-card>
[ESCTP5-W]: <https://support.esicontrols.co.uk/product/esctp5-w>
[ESRTP5WF]: <https://support.esicontrols.co.uk/product/esrtp5wifi>
[ESRTP6B]: <https://support.esicontrols.co.uk/product/stratus-esrtp6b>
[ESRTP6CW]: <https://support.esicontrols.co.uk/product/esrtp6c/>
[esi-controls-async]: <https://pypi.org/project/esi-controls-async/>
[ESI Centro App]: <https://wwwesicontrols.azurewebsites.net/centro.html>
[ESI Portal Heating History dashboard]: <https://esiheating.uksouth.cloudapp.azure.com/portal/UserHeatingHistory>
[Building a Python library for an API]: <https://developers.home-assistant.io/docs/api_lib_index>
