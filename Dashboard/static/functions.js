var data = {}
var start;

$(window).load(function() {
    // $(".loader").fadeOut("slow");
    // $('.loadingBar').stop(true, true)
    // setTimeout(function() {
    //     $('.loadingBar').fadeOut(400)
    // }, 500)
    $('select').each(function() {
        data[this.id] = this.value;
    });
    $("button").each(function() {
        this.addEventListener("click", function(event) {event.preventDefault()})
    });
    var duration = (window.performance.now() - start);
    var time = parseInt((duration/1000)%60)*100;
    document.cookie = "loadTime="+time
    
});
$(document).ready(function(){
    start = window.performance.now();
    var cookie = document.cookie;
    if (cookie != "") {
        var loadTime = parseInt(document.cookie.substring(document.cookie.indexOf('=') + 1))
        if (loadTime < 600) {
            loadTime = 600;
        }
        $('.loadingBar.blue').animate({
            width: '100%'
        }, loadTime);
    }
    else {var loadTime = 600;}
    timer = setTimeout(function() {
        setTimeout(function() {
            $('.loadingBar.blue').fadeOut(400);
        }, 250)
    }, loadTime);

    // CSS adjustments //
    var tabs = $('.tabs').children()
    tabs.each(function() {
        $(this).css({"width": 90 / tabs.length + "%", "margin": "0 " + 7.4 / (tabs.length * 2) + "%"});
    })

    $('input, select').each(function() {
        if ($(this).attr('type') != 'SUBMIT') {
            $(this).attr('id', $(this).siblings('label').first().attr('for'));
        }
        ensureRelevance($(this));
    })

    $('input, select').change(function() {
        checkChanges($(this).attr('id'))
    })

    $(".threeDots").hover(function() {
        $(this).siblings(".hoverDescBox").fadeIn(150);
        $(this).siblings('input, select').first().css('color', 'transparent');
        if (!$(this).siblings("input, select").first().is(":focus")) {
            if ($(this).siblings('.inputOptions').css('display') == 'none') {
                $(this).children().each(function() {
                    $(this).css("border", "5px solid white");
                });
            }
        }
    }, function() {
        $(this).siblings('.hoverDescBox').fadeOut(150);
        $(this).siblings('input, select').first().css('color', 'rgb(202, 66, 66)');
        if (!$(this).siblings("input, select").first().is(":focus")) {
            if ($(this).siblings('.inputOptions').css('display') == 'none') {
                $(this).children().each(function() {
                    $(this).css("border", "5px solid darkgray");
                });
            }
        }
    });

    $(".threeDots").click(function() {
        $(this).children().each(function() {
            $(this).css("border", "5px solid rgb(24, 25, 28)");
        });
        $(this).siblings(".inputOptions").fadeIn(150);
        $(this).siblings("input, select").focus();
        $(this).siblings(".hoverDescBox").fadeOut(150);

    })

    $(".redX").hover(function() {
        if ($(this).next().val() != '1') {
            $(this).parent().css("opacity", "0.5");
        }
    }, function() {
        if ($(this).next().val() != '1') {
            $(this).parent().css("opacity", "1");
        }
    });

    $('.redX').click(function() {
        var subName = $(this).siblings('.inputPod').first().children('input').val();
        var channel = $(this).siblings('.inputPod').first().next().children('select').val();
        var needToHide = subName == '' && channel == '';
        var checked = $(this).next().val() == 1;
        if (checked && !needToHide) {
            $(this).next().val('0');
            $(this).parent().css({'opacity': '1', 'border': '2px solid rgb(24, 25, 28)'});
            $(this).siblings('.inputPod').children('input, select').prop('disabled', false);
        }
        else {
            $(this).next().val('1');
            if (needToHide) {$(this).parent().remove();}
            else {
                $(this).parent().css({'opacity': '0.33', 'border': '2px solid rgb(202, 66, 66)'});
                $(this).siblings('.inputPod').children('input, select').prop('disabled', true);
            }
        }
    })

    $('#redditAddPod').click(function() {
        addRedditPod($(this));
    })

    $(".revertSingle").click(function() {
        var element = $(this).parents().siblings('input, select').first();
        if (element.prop('tagName') == 'INPUT') {
            element.val(element.prop('defaultValue'))
        }
        else {
            element.val(data[element.attr("id")]);
        }
        checkChanges(element.attr('id'));
        redLoadingBar(600);
    })

    $(".resetSingle").click(function() {
        var element = $(this).parents().siblings('input, select').first();
        element.val(element.attr('default'));
        checkChanges(element.attr('id'));
        redLoadingBar(600);
    })

    $(".tab").click(function() {
        var clicked = $(this).attr('id');
        $(".tab").each(function() {
            if ($(this).attr('id') == clicked || $(this).attr('class').includes('selected')) {
                if ($(this).attr('class').includes('selected')) {
                    $('fieldset#' + $(this).attr('id') + 'Settings').toggleClass('selected');
                }
                if (!($(this).attr('id') == clicked && $(this).attr('class').includes('selected'))) {
                    $(this).toggleClass('selected');
                }
            }
        })
        $('fieldset#' + clicked + 'Settings').toggleClass('selected');
    })

    $(document).mousedown(function() {
            $("input, select").blur();
            $(".inputOptions").fadeOut(150);
            $(".threeDots").children().each(function() {
                $(this).css("border", "5px solid darkgray");
            });
    })

    $(":button").click(function() {
        if ($(this).attr("id") == "revert") {
            $('select, input').each(function() {
                checkChanges($(this).attr("id"));
        })}
    });

    $("#settings").submit(function() {
        $("div:not(.loader)").css("opacity", "0.5");
        $(".loader").fadeIn();
    })
});

function redLoadingBar(duration) {
    $('.loadingBar.red').css({'display': 'block', 'width': '0%'});
    $('.loadingBar.red').animate({
            width: '100%'
        }, duration);
    timer = setTimeout(function() {
        setTimeout(function() {
            $('.loadingBar.red').fadeOut(400);
        }, 250)
    }, duration);
}

function defaultVal(id) {
    var element = document.getElementById(id);
    if (element.tagName != "SELECT") {
        var defaultValue = element.defaultValue;
    }
    else {
        var defaultValue = data[id];
    }
    return defaultValue;
}

function checkChanges(id) {
    var element = document.getElementById(id);
    var $element = $('#' + element.id)
    var $pp = $element.parent().parent();
    if (element.type == 'submit') {return;}
    var defaultValue = defaultVal(id);
    if (element.value != defaultValue) {
        $element.parent().css("border-left", "5px solid rgb(89, 89, 248)");
        if ($pp.attr('class') == 'redditFeedPod' && $pp.css('border-left') == '2px solid rgb(24, 25, 28)') { //PP (parent parent) element, or the redditFeedPod, gets highlighted as well if it isn't already
            $pp.css('border-left', '5px solid rgb(89, 89, 248)');
        }
    }
    else {
        $element.parent().css("border-left", "5px solid transparent");
        //Line below this = troublesome
        if ($pp.attr('class') == 'redditFeedPod' && $pp.css('border-left') != '2px solid rgb(24, 25, 28)' && $pp.find('input, select').filter(function() {
            return !['submit', 'checkbox'].includes($element.attr('type')) && $element.val() != defaultVal($element.attr('id'));
        }).length == 0) {
            $pp.css('border-left', '2px solid rgb(24, 25, 28)');
        } 
    }
    //Now, poof away anything that relies on this element being active//
    ensureRelevance($element);
    
}

function ensureRelevance($element) {
    //Hides elements that are irrelevant due to disabled options. This method is also highly ineffecient.//
    $('.inputPod').each(function() {
        if ($(this).attr('reliesOn') == $element.attr('name') && $(this).parent()[0] == $element.parent().parent()[0]) {
            if ([0, '0', '', 'False', 'false', 'colorCode'].includes($element.val()) && $(this).css('display') != 'none') {
                $(this).fadeOut(400);
            }
            else {
                $(this).fadeIn(400);
            }
        }
    })}

function addRedditPod($element) {
    var redditPod = $element.parent().children().first();
    var newPod = redditPod.clone(true);
    newPod.css('display', 'block');
    configureRedditPod(newPod);
    $element.before(newPod);
}

function configureRedditPod($pod) {
    var d = {'subName': '', 'subChannel': '', 'subTruncateTitle': 100, 'subTruncateText': 400, 'subMedia': 3, 'subCreditAuthor': 3, 'subColor': 'colorCode', 'subTimestamp': 'true'};
    var existingPodCount = $('.redditFeedPod').length + 1;
    $pod.children('.inputPod').each(function() {
        $(this).children('input, select').filter(function() {return $(this).attr('tagName') == 'SELECT' || $(this).attr('type') != 'checkbox'}).each(function() {
            $(this).val(d[$(this).attr('name')]);
            var base = $(this).attr('id');
            for (var i = 0; i < base.length; i++) {
                if (['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'].includes(base.substring(i, i+1))) {
                    var numbIndex = i;
                    break;
                }
            }
            $(this).attr('id', base.substring(0, numbIndex) + existingPodCount);
        }) 
        $(this).children('label').each(function() {
            $(this).attr('for', $(this).siblings('input, select').filter(function() {return $(this).attr('tagName') == 'SELECT' || $(this).attr('type') != 'checkbox'}).first().attr('id'));
        })
    })
}

function revertChanges() {
    redLoadingBar(600);
    document.getElementById('settings').reset();
}