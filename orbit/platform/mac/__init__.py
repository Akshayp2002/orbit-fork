"""macOS backend — not implemented yet. Plan, so the shape is clear:

Sources
  rotation : CoreAudio kAudioDevicePropertyVolumeScalar listener on the buds
             output device (AVRCP absolute volume lands there, same 1/16 steps).
             Consume mode restores the level, like Windows.
  clicks   : MPRemoteCommandCenter (play/pause/next/previous) while we publish
             a MPNowPlayingInfoCenter entry and play silence through AVAudioEngine.
  hold     : macOS answers HFP AT+BVRA itself and opens Siri. Options: watch for
             the Siri process / unified log (`log stream --predicate ...`), or a
             PacketLogger-style HCI capture. To be researched.

Output
  keys     : CGEventCreateKeyboardEvent / CGEventPost (needs Accessibility permission)
  scroll   : CGEventCreateScrollWheelEvent
  media    : MRMediaRemoteSendCommand (private) or AppleScript to Music/Spotify
  launch   : `open`

The UI layer (Qt Quick) and the engine are already cross-platform.
"""
from orbit.platform.base import Platform


class MacPlatform(Platform):
    name = "mac"

    def create_sources(self, cfg):
        raise NotImplementedError("macOS backend not built yet — see orbit/platform/mac/__init__.py")

    def create_output(self, cfg):
        raise NotImplementedError("macOS backend not built yet")
