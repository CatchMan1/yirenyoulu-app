import type { NavigatorScreenParams } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { Kind } from './api/types';
export type RootRoutes = {
  Main: NavigatorScreenParams<{ Explore: undefined; Trips: undefined; Me: undefined }> | undefined;
  CityPicker: undefined;
  Catalog: { kind: Kind };
  Place: { id: string };
  Favorites: undefined;
  Trip: { id: string };
  TripForm: { id?: string; placeId?: string } | undefined;
  ItemForm: { tripId: string; itemId?: string; placeId?: string };
  ChooseTrip: { placeId: string; cityId: string };
  Login: undefined;
  Register: undefined;
  Profile: undefined;
  Account: undefined;
};
export type ScreenProps<K extends keyof RootRoutes> = NativeStackScreenProps<RootRoutes, K>;
