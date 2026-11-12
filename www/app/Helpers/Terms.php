<?php
/**
 * Terms helper (#684): what this install calls cruises and lowerings.
 *
 * CRUISE_NAME and LOWERING_NAME in Config.php name them (e.g. Voyage, Dive),
 * and CRUISE_NAME_PLURAL and LOWERING_NAME_PLURAL their plurals. The
 * installer asks for all four. A Config.php from before 2.17 has no plurals,
 * so the name with an "s" is used then. The worker side gets the same names
 * from api/warehouse/getTerms.
 */

namespace Helpers;

class Terms
{
    /**
     * What a cruise is called, e.g. "Cruise" or "Voyage".
     *
     * @param bool $lower for running text: see lower()
     *
     * @return string
     */
    public static function cruise($lower = false)
    {
        return self::form((string) CRUISE_NAME, $lower);
    }

    /**
     * What more than one cruise is called, e.g. "Cruises" or "Voyages".
     *
     * @param bool $lower for running text: see lower()
     *
     * @return string
     */
    public static function cruises($lower = false)
    {
        return self::form(self::plural('CRUISE_NAME_PLURAL', (string) CRUISE_NAME), $lower);
    }

    /**
     * What a lowering is called, e.g. "Lowering" or "Dive".
     *
     * @param bool $lower for running text: see lower()
     *
     * @return string
     */
    public static function lowering($lower = false)
    {
        return self::form((string) LOWERING_NAME, $lower);
    }

    /**
     * What more than one lowering is called, e.g. "Lowerings" or "Dives".
     *
     * @param bool $lower for running text: see lower()
     *
     * @return string
     */
    public static function lowerings($lower = false)
    {
        return self::form(self::plural('LOWERING_NAME_PLURAL', (string) LOWERING_NAME), $lower);
    }

    /**
     * All four names, as api/warehouse/getTerms returns them.
     *
     * @return array cruise, cruises, lowering and lowerings
     */
    public static function all()
    {
        return array(
            'cruise' => self::cruise(),
            'cruises' => self::cruises(),
            'lowering' => self::lowering(),
            'lowerings' => self::lowerings(),
        );
    }

    /**
     * A name as it reads in the middle of a sentence: each word in lower
     * case, except one in capitals, such as an acronym ("ROV Dive" gives
     * "ROV dive").
     *
     * @param string $name the name
     *
     * @return string
     */
    public static function lower($name)
    {
        // Without PHP's mbstring, which the web app otherwise does without
        // (#643), only ASCII letters change case
        $mb = function_exists('mb_strtolower');
        return preg_replace_callback('/[^\s-]+/u', function ($word) use ($mb) {
            $upper = $mb ? mb_strtoupper($word[0]) : strtoupper($word[0]);
            $length = $mb ? mb_strlen($word[0]) : strlen($word[0]);
            if ($upper === $word[0] && $length > 1) {
                return $word[0];
            }
            return $mb ? mb_strtolower($word[0]) : strtolower($word[0]);
        }, (string) $name);
    }

    /**
     * The plural constant, or the name with an "s" without one.
     *
     * @param string $constant the plural's constant name
     * @param string $singular the singular name
     *
     * @return string
     */
    private static function plural($constant, $singular)
    {
        return defined($constant) ? (string) constant($constant) : $singular . 's';
    }

    /**
     * The name as given, or lower()'s form of it.
     *
     * @param string $name  the name
     * @param bool   $lower whether to give lower()'s form
     *
     * @return string
     */
    private static function form($name, $lower)
    {
        return $lower ? self::lower($name) : $name;
    }
}
