// Web-only adaptations to the user's licensed stock menu. No game GUI assets
// are copied into the port; unknown/mod controls retain their original behavior.
#ifndef WEB_MENU_POLICY_H
#define WEB_MENU_POLICY_H

struct webMenuChoice_t {
	const char *window, *originalCvar, *titleWindow, *title;
	const char *choices, *replacementCvar;
	bool readOnly;
	const char *values;
};

static inline bool Web_MenuOnScreen(float x, float y, float w, float h) {
	return w > 0 && h > 0 && x < 640 && y < 480 && x + w > 0 && y + h > 0;
}

static const webMenuChoice_t webMenuChoices[] = {
	{ "OS2Primary", "r_mode", "OS2Title", "Render size", "Browser", NULL, true, NULL },
	{ "OS3Primary", "r_fullscreen", "OS3Title", "Display mode", "Browser", NULL, true, NULL },
	{ "OS6Primary", "s_numberOfSpeakers", "OS6Title", "Speakers", "Stereo", NULL, true, NULL },
	{ "EAXPrimary", "s_useEAXReverb", "EAXTitle", "EAX N/A", "Off", NULL, true, NULL },
	{ "SNDBPrimary", "s_driver", "SNDBTitle", "Audio backend", "WebAudio", NULL, true, NULL },
	{ "ADV5Primary", "r_swapInterval", "ADV5Title", "Frame rate", "30 FPS;60 FPS;Unlocked", "r_webFrameLimit", false, "30;60;0" },
	{ "ADV7Primary", "r_multisamples", "ADV7Title", "Soft particles", "On;Off", "r_useSoftParticles", false, "1;0" }
};

static inline bool Web_IsStockMenu(const char *source) {
	return source && (!idStr::Icmp(source, "guis/mainmenu.gui") ||
		!idStr::Icmp(source, "guis/demo_mainmenu.gui"));
}

static inline const webMenuChoice_t *Web_MenuChoice(const char *source, const char *window, const char *cvar) {
	if (!Web_IsStockMenu(source) || !window || !cvar) return NULL;
	for (const webMenuChoice_t &option : webMenuChoices) {
		if (!idStr::Icmp(window, option.window) && !idStr::Icmp(cvar, option.originalCvar)) return &option;
	}
	return NULL;
}

#endif
