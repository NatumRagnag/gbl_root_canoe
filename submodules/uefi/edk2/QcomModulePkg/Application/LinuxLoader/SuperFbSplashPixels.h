/* Fixed layout for the user's 890x1920 artwork on a 1200x2608 screen.
 * Integer bilinear interpolation, 48-pixel side margins, no cropping/stretch.
 * Types UINT8/UINT32/UINTN are supplied by UEFI or the host test harness.
 */
#ifndef SFB_SPLASH_PIXELS_H
#define SFB_SPLASH_PIXELS_H
#define SFB_ART_WIDTH 890U
#define SFB_ART_HEIGHT 1920U
#define SFB_ART_BYTES (SFB_ART_WIDTH * SFB_ART_HEIGHT * 4U)
#define SFB_SCREEN_WIDTH 1200U
#define SFB_SCREEN_HEIGHT 2608U
#define SFB_DRAW_WIDTH 1104U
#define SFB_DRAW_HEIGHT (SFB_ART_HEIGHT * SFB_DRAW_WIDTH / SFB_ART_WIDTH)

STATIC VOID
SfbScaleSplash (IN CONST UINT8 *Source, OUT UINT8 *Screen)
{
  UINT32 X, Y, C, Sx, Sy, Fx, Fy, X0, X1, Y0, Y1, Top, Bottom;
  UINTN Dest;
  for (Y = 0; Y < SFB_DRAW_HEIGHT; Y++) {
    Sy = Y * (SFB_ART_HEIGHT - 1) * 256U / (SFB_DRAW_HEIGHT - 1);
    Y0 = Sy >> 8; Y1 = Y0 + (Y0 < SFB_ART_HEIGHT - 1); Fy = Sy & 255;
    for (X = 0; X < SFB_DRAW_WIDTH; X++) {
      Sx = X * (SFB_ART_WIDTH - 1) * 256U / (SFB_DRAW_WIDTH - 1);
      X0 = Sx >> 8; X1 = X0 + (X0 < SFB_ART_WIDTH - 1); Fx = Sx & 255;
      Dest = (((SFB_SCREEN_HEIGHT - SFB_DRAW_HEIGHT) / 2 + Y) * SFB_SCREEN_WIDTH + 48 + X) * 4;
      for (C = 0; C < 3; C++) {
        Top = Source[(Y0 * SFB_ART_WIDTH + X0) * 4 + C] * (256 - Fx) +
              Source[(Y0 * SFB_ART_WIDTH + X1) * 4 + C] * Fx;
        Bottom = Source[(Y1 * SFB_ART_WIDTH + X0) * 4 + C] * (256 - Fx) +
                 Source[(Y1 * SFB_ART_WIDTH + X1) * 4 + C] * Fx;
        Screen[Dest + C] = (UINT8)((Top * (256 - Fy) + Bottom * Fy + 32768) >> 16);
      }
    }
  }
}
#endif
