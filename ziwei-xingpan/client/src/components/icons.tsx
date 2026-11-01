import { View, Image } from '@tarojs/components';
import './icons.scss';

// Lucide icons as rasterized PNGs (see scripts/lucide-rasterize.cjs).
// WeChat <image> cannot render SVG, so the official Lucide paths
// (lucide-static v1.66.0, ISC, under src/assets/lucide/svg/) are baked
// to transparent 144px PNGs in four stroke tones. Tones: blue = light
// primary #346bf0, sky = dark primary #8db4ff, gray = inactive
// #9a9ba2, white = on-gradient #ffffff. config/index.ts forces file
// emission (imageUrlLoaderOption.limit = true) so no icon is inlined
// as base64, which <image> cannot display.
import ic_home_blue from '../assets/lucide/png/home-blue.png';
import ic_home_sky from '../assets/lucide/png/home-sky.png';
import ic_home_gray from '../assets/lucide/png/home-gray.png';
import ic_home_white from '../assets/lucide/png/home-white.png';
import ic_message_circle_blue from '../assets/lucide/png/message-circle-blue.png';
import ic_message_circle_sky from '../assets/lucide/png/message-circle-sky.png';
import ic_message_circle_gray from '../assets/lucide/png/message-circle-gray.png';
import ic_message_circle_white from '../assets/lucide/png/message-circle-white.png';
import ic_book_open_blue from '../assets/lucide/png/book-open-blue.png';
import ic_book_open_sky from '../assets/lucide/png/book-open-sky.png';
import ic_book_open_gray from '../assets/lucide/png/book-open-gray.png';
import ic_book_open_white from '../assets/lucide/png/book-open-white.png';
import ic_user_blue from '../assets/lucide/png/user-blue.png';
import ic_user_sky from '../assets/lucide/png/user-sky.png';
import ic_user_gray from '../assets/lucide/png/user-gray.png';
import ic_user_white from '../assets/lucide/png/user-white.png';
import ic_users_blue from '../assets/lucide/png/users-blue.png';
import ic_users_sky from '../assets/lucide/png/users-sky.png';
import ic_users_gray from '../assets/lucide/png/users-gray.png';
import ic_users_white from '../assets/lucide/png/users-white.png';
import ic_user_plus_blue from '../assets/lucide/png/user-plus-blue.png';
import ic_user_plus_sky from '../assets/lucide/png/user-plus-sky.png';
import ic_user_plus_gray from '../assets/lucide/png/user-plus-gray.png';
import ic_user_plus_white from '../assets/lucide/png/user-plus-white.png';
import ic_crown_blue from '../assets/lucide/png/crown-blue.png';
import ic_crown_sky from '../assets/lucide/png/crown-sky.png';
import ic_crown_gray from '../assets/lucide/png/crown-gray.png';
import ic_crown_white from '../assets/lucide/png/crown-white.png';
import ic_coins_blue from '../assets/lucide/png/coins-blue.png';
import ic_coins_sky from '../assets/lucide/png/coins-sky.png';
import ic_coins_gray from '../assets/lucide/png/coins-gray.png';
import ic_coins_white from '../assets/lucide/png/coins-white.png';
import ic_history_blue from '../assets/lucide/png/history-blue.png';
import ic_history_sky from '../assets/lucide/png/history-sky.png';
import ic_history_gray from '../assets/lucide/png/history-gray.png';
import ic_history_white from '../assets/lucide/png/history-white.png';
import ic_layers_blue from '../assets/lucide/png/layers-blue.png';
import ic_layers_sky from '../assets/lucide/png/layers-sky.png';
import ic_layers_gray from '../assets/lucide/png/layers-gray.png';
import ic_layers_white from '../assets/lucide/png/layers-white.png';
import ic_share_2_blue from '../assets/lucide/png/share-2-blue.png';
import ic_share_2_sky from '../assets/lucide/png/share-2-sky.png';
import ic_share_2_gray from '../assets/lucide/png/share-2-gray.png';
import ic_share_2_white from '../assets/lucide/png/share-2-white.png';
import ic_clipboard_list_blue from '../assets/lucide/png/clipboard-list-blue.png';
import ic_clipboard_list_sky from '../assets/lucide/png/clipboard-list-sky.png';
import ic_clipboard_list_gray from '../assets/lucide/png/clipboard-list-gray.png';
import ic_clipboard_list_white from '../assets/lucide/png/clipboard-list-white.png';
import ic_settings_blue from '../assets/lucide/png/settings-blue.png';
import ic_settings_sky from '../assets/lucide/png/settings-sky.png';
import ic_settings_gray from '../assets/lucide/png/settings-gray.png';
import ic_settings_white from '../assets/lucide/png/settings-white.png';
import ic_message_square_blue from '../assets/lucide/png/message-square-blue.png';
import ic_message_square_sky from '../assets/lucide/png/message-square-sky.png';
import ic_message_square_gray from '../assets/lucide/png/message-square-gray.png';
import ic_message_square_white from '../assets/lucide/png/message-square-white.png';
import ic_info_blue from '../assets/lucide/png/info-blue.png';
import ic_info_sky from '../assets/lucide/png/info-sky.png';
import ic_info_gray from '../assets/lucide/png/info-gray.png';
import ic_info_white from '../assets/lucide/png/info-white.png';
import ic_layout_grid_blue from '../assets/lucide/png/layout-grid-blue.png';
import ic_layout_grid_sky from '../assets/lucide/png/layout-grid-sky.png';
import ic_layout_grid_gray from '../assets/lucide/png/layout-grid-gray.png';
import ic_layout_grid_white from '../assets/lucide/png/layout-grid-white.png';
import ic_log_in_blue from '../assets/lucide/png/log-in-blue.png';
import ic_log_in_sky from '../assets/lucide/png/log-in-sky.png';
import ic_log_in_gray from '../assets/lucide/png/log-in-gray.png';
import ic_log_in_white from '../assets/lucide/png/log-in-white.png';
import ic_log_out_blue from '../assets/lucide/png/log-out-blue.png';
import ic_log_out_sky from '../assets/lucide/png/log-out-sky.png';
import ic_log_out_gray from '../assets/lucide/png/log-out-gray.png';
import ic_log_out_white from '../assets/lucide/png/log-out-white.png';
import ic_refresh_cw_blue from '../assets/lucide/png/refresh-cw-blue.png';
import ic_refresh_cw_sky from '../assets/lucide/png/refresh-cw-sky.png';
import ic_refresh_cw_gray from '../assets/lucide/png/refresh-cw-gray.png';
import ic_refresh_cw_white from '../assets/lucide/png/refresh-cw-white.png';
import ic_chevron_right_blue from '../assets/lucide/png/chevron-right-blue.png';
import ic_chevron_right_sky from '../assets/lucide/png/chevron-right-sky.png';
import ic_chevron_right_gray from '../assets/lucide/png/chevron-right-gray.png';
import ic_chevron_right_white from '../assets/lucide/png/chevron-right-white.png';
import ic_chevron_left_blue from '../assets/lucide/png/chevron-left-blue.png';
import ic_chevron_left_sky from '../assets/lucide/png/chevron-left-sky.png';
import ic_chevron_left_gray from '../assets/lucide/png/chevron-left-gray.png';
import ic_chevron_left_white from '../assets/lucide/png/chevron-left-white.png';
import ic_copy_blue from '../assets/lucide/png/copy-blue.png';
import ic_copy_sky from '../assets/lucide/png/copy-sky.png';
import ic_copy_gray from '../assets/lucide/png/copy-gray.png';
import ic_copy_white from '../assets/lucide/png/copy-white.png';
import ic_check_blue from '../assets/lucide/png/check-blue.png';
import ic_check_sky from '../assets/lucide/png/check-sky.png';
import ic_check_gray from '../assets/lucide/png/check-gray.png';
import ic_check_white from '../assets/lucide/png/check-white.png';
import ic_trash_2_blue from '../assets/lucide/png/trash-2-blue.png';
import ic_trash_2_sky from '../assets/lucide/png/trash-2-sky.png';
import ic_trash_2_gray from '../assets/lucide/png/trash-2-gray.png';
import ic_trash_2_white from '../assets/lucide/png/trash-2-white.png';
import ic_maximize_2_blue from '../assets/lucide/png/maximize-2-blue.png';
import ic_maximize_2_sky from '../assets/lucide/png/maximize-2-sky.png';
import ic_maximize_2_gray from '../assets/lucide/png/maximize-2-gray.png';
import ic_maximize_2_white from '../assets/lucide/png/maximize-2-white.png';
import ic_x_blue from '../assets/lucide/png/x-blue.png';
import ic_x_sky from '../assets/lucide/png/x-sky.png';
import ic_x_gray from '../assets/lucide/png/x-gray.png';
import ic_x_white from '../assets/lucide/png/x-white.png';
import ic_eye_blue from '../assets/lucide/png/eye-blue.png';
import ic_eye_sky from '../assets/lucide/png/eye-sky.png';
import ic_eye_gray from '../assets/lucide/png/eye-gray.png';
import ic_eye_white from '../assets/lucide/png/eye-white.png';
import ic_eye_off_blue from '../assets/lucide/png/eye-off-blue.png';
import ic_eye_off_sky from '../assets/lucide/png/eye-off-sky.png';
import ic_eye_off_gray from '../assets/lucide/png/eye-off-gray.png';
import ic_eye_off_white from '../assets/lucide/png/eye-off-white.png';
import ic_mail_blue from '../assets/lucide/png/mail-blue.png';
import ic_mail_sky from '../assets/lucide/png/mail-sky.png';
import ic_mail_gray from '../assets/lucide/png/mail-gray.png';
import ic_mail_white from '../assets/lucide/png/mail-white.png';
import ic_lock_blue from '../assets/lucide/png/lock-blue.png';
import ic_lock_sky from '../assets/lucide/png/lock-sky.png';
import ic_lock_gray from '../assets/lucide/png/lock-gray.png';
import ic_lock_white from '../assets/lucide/png/lock-white.png';
import ic_chrome_blue from '../assets/lucide/png/chrome-blue.png';
import ic_chrome_sky from '../assets/lucide/png/chrome-sky.png';
import ic_chrome_gray from '../assets/lucide/png/chrome-gray.png';
import ic_chrome_white from '../assets/lucide/png/chrome-white.png';
import ic_apple_blue from '../assets/lucide/png/apple-blue.png';
import ic_apple_sky from '../assets/lucide/png/apple-sky.png';
import ic_apple_gray from '../assets/lucide/png/apple-gray.png';
import ic_apple_white from '../assets/lucide/png/apple-white.png';
import ic_calendar_blue from '../assets/lucide/png/calendar-blue.png';
import ic_calendar_sky from '../assets/lucide/png/calendar-sky.png';
import ic_calendar_gray from '../assets/lucide/png/calendar-gray.png';
import ic_calendar_white from '../assets/lucide/png/calendar-white.png';
import ic_map_pin_blue from '../assets/lucide/png/map-pin-blue.png';
import ic_map_pin_sky from '../assets/lucide/png/map-pin-sky.png';
import ic_map_pin_gray from '../assets/lucide/png/map-pin-gray.png';
import ic_map_pin_white from '../assets/lucide/png/map-pin-white.png';
import ic_clock_blue from '../assets/lucide/png/clock-blue.png';
import ic_clock_sky from '../assets/lucide/png/clock-sky.png';
import ic_clock_gray from '../assets/lucide/png/clock-gray.png';
import ic_clock_white from '../assets/lucide/png/clock-white.png';
import ic_sparkles_blue from '../assets/lucide/png/sparkles-blue.png';
import ic_sparkles_sky from '../assets/lucide/png/sparkles-sky.png';
import ic_sparkles_gray from '../assets/lucide/png/sparkles-gray.png';
import ic_sparkles_white from '../assets/lucide/png/sparkles-white.png';
import ic_arrow_up_blue from '../assets/lucide/png/arrow-up-blue.png';
import ic_arrow_up_sky from '../assets/lucide/png/arrow-up-sky.png';
import ic_arrow_up_gray from '../assets/lucide/png/arrow-up-gray.png';
import ic_arrow_up_white from '../assets/lucide/png/arrow-up-white.png';
import ic_arrow_right_blue from '../assets/lucide/png/arrow-right-blue.png';
import ic_arrow_right_sky from '../assets/lucide/png/arrow-right-sky.png';
import ic_arrow_right_gray from '../assets/lucide/png/arrow-right-gray.png';
import ic_arrow_right_white from '../assets/lucide/png/arrow-right-white.png';
import ic_moon_blue from '../assets/lucide/png/moon-blue.png';
import ic_moon_sky from '../assets/lucide/png/moon-sky.png';
import ic_moon_gray from '../assets/lucide/png/moon-gray.png';
import ic_moon_white from '../assets/lucide/png/moon-white.png';
import ic_sun_blue from '../assets/lucide/png/sun-blue.png';
import ic_sun_sky from '../assets/lucide/png/sun-sky.png';
import ic_sun_gray from '../assets/lucide/png/sun-gray.png';
import ic_sun_white from '../assets/lucide/png/sun-white.png';
import ic_inbox_blue from '../assets/lucide/png/inbox-blue.png';
import ic_inbox_sky from '../assets/lucide/png/inbox-sky.png';
import ic_inbox_gray from '../assets/lucide/png/inbox-gray.png';
import ic_inbox_white from '../assets/lucide/png/inbox-white.png';
import ic_star_blue from '../assets/lucide/png/star-blue.png';
import ic_star_sky from '../assets/lucide/png/star-sky.png';
import ic_star_gray from '../assets/lucide/png/star-gray.png';
import ic_star_white from '../assets/lucide/png/star-white.png';
import ic_gift_blue from '../assets/lucide/png/gift-blue.png';
import ic_gift_sky from '../assets/lucide/png/gift-sky.png';
import ic_gift_gray from '../assets/lucide/png/gift-gray.png';
import ic_gift_white from '../assets/lucide/png/gift-white.png';
import ic_pen_line_blue from '../assets/lucide/png/pen-line-blue.png';
import ic_pen_line_sky from '../assets/lucide/png/pen-line-sky.png';
import ic_pen_line_gray from '../assets/lucide/png/pen-line-gray.png';
import ic_pen_line_white from '../assets/lucide/png/pen-line-white.png';
import ic_zap_blue from '../assets/lucide/png/zap-blue.png';
import ic_zap_sky from '../assets/lucide/png/zap-sky.png';
import ic_zap_gray from '../assets/lucide/png/zap-gray.png';
import ic_zap_white from '../assets/lucide/png/zap-white.png';
import ic_save_blue from '../assets/lucide/png/save-blue.png';
import ic_save_sky from '../assets/lucide/png/save-sky.png';
import ic_save_gray from '../assets/lucide/png/save-gray.png';
import ic_save_white from '../assets/lucide/png/save-white.png';
import ic_search_blue from '../assets/lucide/png/search-blue.png';
import ic_search_sky from '../assets/lucide/png/search-sky.png';
import ic_search_gray from '../assets/lucide/png/search-gray.png';
import ic_search_white from '../assets/lucide/png/search-white.png';
import ic_plus_blue from '../assets/lucide/png/plus-blue.png';
import ic_plus_sky from '../assets/lucide/png/plus-sky.png';
import ic_plus_gray from '../assets/lucide/png/plus-gray.png';
import ic_plus_white from '../assets/lucide/png/plus-white.png';
import ic_minus_blue from '../assets/lucide/png/minus-blue.png';
import ic_minus_sky from '../assets/lucide/png/minus-sky.png';
import ic_minus_gray from '../assets/lucide/png/minus-gray.png';
import ic_minus_white from '../assets/lucide/png/minus-white.png';

export const ICON_NAMES = ['home', 'message-circle', 'book-open', 'user', 'users', 'user-plus', 'crown', 'coins', 'history', 'layers', 'share-2', 'clipboard-list', 'settings', 'message-square', 'info', 'layout-grid', 'log-in', 'log-out', 'refresh-cw', 'chevron-right', 'chevron-left', 'copy', 'check', 'trash-2', 'maximize-2', 'x', 'eye', 'eye-off', 'mail', 'lock', 'chrome', 'apple', 'calendar', 'map-pin', 'clock', 'sparkles', 'arrow-up', 'arrow-right', 'moon', 'sun', 'inbox', 'star', 'gift', 'pen-line', 'zap', 'save', 'search', 'plus', 'minus'] as const;
export type IconName = typeof ICON_NAMES[number];
export type IconTone = 'blue' | 'sky' | 'gray' | 'white';
const SRC: Record<IconName, Record<IconTone, string>> = {
  'home': { blue: ic_home_blue, sky: ic_home_sky, gray: ic_home_gray, white: ic_home_white },
  'message-circle': { blue: ic_message_circle_blue, sky: ic_message_circle_sky, gray: ic_message_circle_gray, white: ic_message_circle_white },
  'book-open': { blue: ic_book_open_blue, sky: ic_book_open_sky, gray: ic_book_open_gray, white: ic_book_open_white },
  'user': { blue: ic_user_blue, sky: ic_user_sky, gray: ic_user_gray, white: ic_user_white },
  'users': { blue: ic_users_blue, sky: ic_users_sky, gray: ic_users_gray, white: ic_users_white },
  'user-plus': { blue: ic_user_plus_blue, sky: ic_user_plus_sky, gray: ic_user_plus_gray, white: ic_user_plus_white },
  'crown': { blue: ic_crown_blue, sky: ic_crown_sky, gray: ic_crown_gray, white: ic_crown_white },
  'coins': { blue: ic_coins_blue, sky: ic_coins_sky, gray: ic_coins_gray, white: ic_coins_white },
  'history': { blue: ic_history_blue, sky: ic_history_sky, gray: ic_history_gray, white: ic_history_white },
  'layers': { blue: ic_layers_blue, sky: ic_layers_sky, gray: ic_layers_gray, white: ic_layers_white },
  'share-2': { blue: ic_share_2_blue, sky: ic_share_2_sky, gray: ic_share_2_gray, white: ic_share_2_white },
  'clipboard-list': { blue: ic_clipboard_list_blue, sky: ic_clipboard_list_sky, gray: ic_clipboard_list_gray, white: ic_clipboard_list_white },
  'settings': { blue: ic_settings_blue, sky: ic_settings_sky, gray: ic_settings_gray, white: ic_settings_white },
  'message-square': { blue: ic_message_square_blue, sky: ic_message_square_sky, gray: ic_message_square_gray, white: ic_message_square_white },
  'info': { blue: ic_info_blue, sky: ic_info_sky, gray: ic_info_gray, white: ic_info_white },
  'layout-grid': { blue: ic_layout_grid_blue, sky: ic_layout_grid_sky, gray: ic_layout_grid_gray, white: ic_layout_grid_white },
  'log-in': { blue: ic_log_in_blue, sky: ic_log_in_sky, gray: ic_log_in_gray, white: ic_log_in_white },
  'log-out': { blue: ic_log_out_blue, sky: ic_log_out_sky, gray: ic_log_out_gray, white: ic_log_out_white },
  'refresh-cw': { blue: ic_refresh_cw_blue, sky: ic_refresh_cw_sky, gray: ic_refresh_cw_gray, white: ic_refresh_cw_white },
  'chevron-right': { blue: ic_chevron_right_blue, sky: ic_chevron_right_sky, gray: ic_chevron_right_gray, white: ic_chevron_right_white },
  'chevron-left': { blue: ic_chevron_left_blue, sky: ic_chevron_left_sky, gray: ic_chevron_left_gray, white: ic_chevron_left_white },
  'copy': { blue: ic_copy_blue, sky: ic_copy_sky, gray: ic_copy_gray, white: ic_copy_white },
  'check': { blue: ic_check_blue, sky: ic_check_sky, gray: ic_check_gray, white: ic_check_white },
  'trash-2': { blue: ic_trash_2_blue, sky: ic_trash_2_sky, gray: ic_trash_2_gray, white: ic_trash_2_white },
  'maximize-2': { blue: ic_maximize_2_blue, sky: ic_maximize_2_sky, gray: ic_maximize_2_gray, white: ic_maximize_2_white },
  'x': { blue: ic_x_blue, sky: ic_x_sky, gray: ic_x_gray, white: ic_x_white },
  'eye': { blue: ic_eye_blue, sky: ic_eye_sky, gray: ic_eye_gray, white: ic_eye_white },
  'eye-off': { blue: ic_eye_off_blue, sky: ic_eye_off_sky, gray: ic_eye_off_gray, white: ic_eye_off_white },
  'mail': { blue: ic_mail_blue, sky: ic_mail_sky, gray: ic_mail_gray, white: ic_mail_white },
  'lock': { blue: ic_lock_blue, sky: ic_lock_sky, gray: ic_lock_gray, white: ic_lock_white },
  'chrome': { blue: ic_chrome_blue, sky: ic_chrome_sky, gray: ic_chrome_gray, white: ic_chrome_white },
  'apple': { blue: ic_apple_blue, sky: ic_apple_sky, gray: ic_apple_gray, white: ic_apple_white },
  'calendar': { blue: ic_calendar_blue, sky: ic_calendar_sky, gray: ic_calendar_gray, white: ic_calendar_white },
  'map-pin': { blue: ic_map_pin_blue, sky: ic_map_pin_sky, gray: ic_map_pin_gray, white: ic_map_pin_white },
  'clock': { blue: ic_clock_blue, sky: ic_clock_sky, gray: ic_clock_gray, white: ic_clock_white },
  'sparkles': { blue: ic_sparkles_blue, sky: ic_sparkles_sky, gray: ic_sparkles_gray, white: ic_sparkles_white },
  'arrow-up': { blue: ic_arrow_up_blue, sky: ic_arrow_up_sky, gray: ic_arrow_up_gray, white: ic_arrow_up_white },
  'arrow-right': { blue: ic_arrow_right_blue, sky: ic_arrow_right_sky, gray: ic_arrow_right_gray, white: ic_arrow_right_white },
  'moon': { blue: ic_moon_blue, sky: ic_moon_sky, gray: ic_moon_gray, white: ic_moon_white },
  'sun': { blue: ic_sun_blue, sky: ic_sun_sky, gray: ic_sun_gray, white: ic_sun_white },
  'inbox': { blue: ic_inbox_blue, sky: ic_inbox_sky, gray: ic_inbox_gray, white: ic_inbox_white },
  'star': { blue: ic_star_blue, sky: ic_star_sky, gray: ic_star_gray, white: ic_star_white },
  'gift': { blue: ic_gift_blue, sky: ic_gift_sky, gray: ic_gift_gray, white: ic_gift_white },
  'pen-line': { blue: ic_pen_line_blue, sky: ic_pen_line_sky, gray: ic_pen_line_gray, white: ic_pen_line_white },
  'zap': { blue: ic_zap_blue, sky: ic_zap_sky, gray: ic_zap_gray, white: ic_zap_white },
  'save': { blue: ic_save_blue, sky: ic_save_sky, gray: ic_save_gray, white: ic_save_white },
  'search': { blue: ic_search_blue, sky: ic_search_sky, gray: ic_search_gray, white: ic_search_white },
  'plus': { blue: ic_plus_blue, sky: ic_plus_sky, gray: ic_plus_gray, white: ic_plus_white },
  'minus': { blue: ic_minus_blue, sky: ic_minus_sky, gray: ic_minus_gray, white: ic_minus_white },
};

export function Icon({ name, tone, size }: { name: IconName; tone: IconTone; size?: string }) {
  return <Image className='lucide-icon' style={{ width: size || '40px', height: size || '40px' }} src={SRC[name][tone]} mode='aspectFit' />;
}

// Service-row badge: soft blue rounded square + blue glyph (light) or
// soft dark-blue square + sky glyph (dark). Replaces the old colored
// dot placeholders, which carried no glyph at all.
export function IconBadge({ name, dark }: { name: IconName; dark?: boolean }) {
  return (
    <View className={dark ? 'icon-badge icon-badge-dark' : 'icon-badge'}>
      <Icon name={name} tone={dark ? 'sky' : 'blue'} size='40px' />
    </View>
  );
}
