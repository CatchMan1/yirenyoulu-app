import { Alert as NativeAlert, Platform } from 'react-native';
/** Browser previews use native browser confirmation; iOS keeps platform dialogs. */
export const Dialog: Pick<typeof NativeAlert, 'alert'> = {
  alert: (title, message, buttons, options) => {
    if (Platform.OS !== 'web') {
      NativeAlert.alert(title, message, buttons, options);
      return;
    }
    const text = [title, message].filter(Boolean).join('\n');
    const accept = buttons?.find((button) => button.style !== 'cancel');
    const cancel = buttons?.find((button) => button.style === 'cancel');
    if (accept) {
      if (globalThis.confirm(text)) accept.onPress?.();
      else cancel?.onPress?.();
    } else globalThis.alert(text);
  },
};
