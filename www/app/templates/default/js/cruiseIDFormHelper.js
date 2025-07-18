$(function () {
	'use strict';

	$('select[name=cruiseID]').change(function () {
		$("input[name=cruiseName]").prop('disabled', true);
		$("input[name=cruiseStartDate]").prop('disabled', true);
		$("input[name=cruiseEndDate]").prop('disabled', true);
		$("input[name=cruiseStartPort]").prop('disabled', true);
		$("input[name=cruiseEndPort]").prop('disabled', true);
		$("input[name=cruisePI]").prop('disabled', true);
		$("input[name=cruiseLocation]").prop('disabled', true);
    });

	$('input[name=cruiseName]').on('input', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

	$('input[name=cruiseStartDate]').on('input', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

	$('#cruiseStartDate').on('dp.change', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

	$('input[name=cruiseEndDate]').on('input', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

	$('#cruiseEndDate').on('dp.change', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

	$('input[name=cruiseStartPort]').on('input', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

	$('input[name=cruiseEndPort]').on('input', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

	$('input[name=cruisePI]').on('input', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

	$('input[name=cruiseLocation]').on('input', function () {
		$("select[name=cruiseID]").prop('disabled', true);
	});

})